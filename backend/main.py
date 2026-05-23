import json
import os
import time
from collections import defaultdict
from pathlib import Path

import stripe
import jwt
from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from openai import OpenAI
from passlib.context import CryptContext
from pydantic import BaseModel
from dotenv import load_dotenv

from db import (
    create_user, get_user_by_email, get_user_by_id, get_user_by_customer_id,
    update_subscription, init_db, update_password,
    load_user_config, save_user_config, load_user_knowledge, save_user_knowledge,
    set_email_verified, increment_conversations,
)

load_dotenv()

BASE_DIR     = Path(__file__).parent
FRONTEND_DIR = Path(os.getenv("FRONTEND_DIR", str(BASE_DIR.parent / "frontend")))
PORT         = int(os.getenv("PORT", 8000))
SECRET_KEY   = os.getenv("SECRET_KEY", "change-me-in-production")
stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

app = FastAPI(title="Répondly")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), base_url=os.getenv("OPENAI_BASE_URL"))

SYSTEM_PROMPT_TEMPLATE = """Tu es {bot_name}, l'assistant(e) virtuel(le) de {bot_business}.

RÈGLES ABSOLUES :
- Réponds TOUJOURS en {language}
- Ton chaleureux, professionnel, concis — maximum 3 phrases par réponse
- Base-toi UNIQUEMENT sur les informations du catalogue ci-dessous
- Si une question sort de ton périmètre, réponds exactement : "Je transmets ça à notre équipe, tu auras une réponse sous 24h. Quel est ton email ?"
- Ne fabrique jamais d'information qui n'est pas dans le catalogue
- Ne mentionne jamais que tu es une IA

CATALOGUE :
{knowledge}
"""


# ── Rate limiter (in-memory, 100 req/hour per bot) ──────────────
_rate_windows: dict[str, list[float]] = defaultdict(list)
RATE_LIMIT_PER_HOUR = int(os.getenv("CHAT_RATE_LIMIT", "100"))

def _check_rate_limit(bot_id: str) -> bool:
    now = time.time()
    window = [t for t in _rate_windows[bot_id] if now - t < 3600]
    _rate_windows[bot_id] = window
    if len(window) >= RATE_LIMIT_PER_HOUR:
        return False
    _rate_windows[bot_id].append(now)
    return True


# ── Auth helpers ────────────────────────────────────────────────

def make_token(user_id: str) -> str:
    return jwt.encode({"sub": user_id}, SECRET_KEY, algorithm="HS256")


def decode_token(token: str) -> str | None:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=["HS256"])["sub"]
    except Exception:
        return None


def get_current_user_id(request: Request) -> str | None:
    token = request.cookies.get("session")
    return decode_token(token) if token else None


# ── Per-user data ────────────────────────────────────────────────

_CONFIG_DEFAULTS = {"bot_name": "Assistant", "bot_business": "votre entreprise", "bot_language": "français", "accent_color": "#c9a84c"}

def load_config(user_id: str) -> dict:
    return {**_CONFIG_DEFAULTS, **load_user_config(user_id)}

def load_knowledge(user_id: str) -> str:
    return json.dumps(load_user_knowledge(user_id), ensure_ascii=False, indent=2)

def save_config(user_id: str, config: dict):
    save_user_config(user_id, config)

def save_knowledge(user_id: str, knowledge: dict):
    save_user_knowledge(user_id, knowledge)


# ── Password reset ──────────────────────────────────────────────

def make_verify_token(user_id: str) -> str:
    return jwt.encode({"sub": user_id, "type": "verify"}, SECRET_KEY, algorithm="HS256")


def decode_verify_token(token: str) -> str | None:
    try:
        data = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        if data.get("type") != "verify":
            return None
        return data["sub"]
    except Exception:
        return None


def make_reset_token(user_id: str) -> str:
    import time
    return jwt.encode({"sub": user_id, "type": "reset", "exp": int(time.time()) + 3600}, SECRET_KEY, algorithm="HS256")


def decode_reset_token(token: str) -> str | None:
    try:
        data = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        if data.get("type") != "reset":
            return None
        return data["sub"]
    except Exception:
        return None


def send_email(to_email: str, subject: str, body: str) -> bool:
    import urllib.request
    import json as _json
    api_key   = os.getenv("BREVO_API_KEY", "")
    from_addr = os.getenv("SMTP_FROM", "matissezamcre@gmail.com")
    print(f"[EMAIL] to={to_email} from={from_addr!r} api_key_prefix={api_key[:12]!r}")
    if not api_key:
        print("[EMAIL] BREVO_API_KEY not set — skipping")
        return False
    payload = _json.dumps({
        "sender": {"email": from_addr},
        "to": [{"email": to_email}],
        "subject": subject,
        "textContent": body,
    }).encode()
    req = urllib.request.Request(
        "https://api.brevo.com/v3/smtp/email",
        data=payload,
        headers={"api-key": api_key, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            print(f"[EMAIL] Sent OK status={r.status}")
        return True
    except Exception as e:
        print(f"[EMAIL] Error: {e}")
        return False


@app.post("/resend-verify")
async def resend_verify(request: Request):
    user_id = get_current_user_id(request)
    if not user_id:
        return JSONResponse({"error": "unauthenticated"}, status_code=401)
    user = get_user_by_id(user_id)
    token = make_verify_token(user_id)
    base = os.getenv("APP_URL", str(request.base_url).rstrip("/"))
    verify_url = f"{base}/verify-email?token={token}"
    send_email(user["email"], "Vérifiez votre email Répondly", f"Cliquez sur ce lien pour vérifier votre email :\n\n{verify_url}")
    return {"ok": True}


@app.get("/verify-email")
async def verify_email(token: str = Query(...)):
    user_id = decode_verify_token(token)
    if not user_id:
        return HTMLResponse("Lien invalide ou expiré. <a href='/dashboard'>Dashboard</a>", status_code=400)
    set_email_verified(user_id)
    return RedirectResponse("/dashboard?verified=1", status_code=302)


@app.get("/forgot-password")
async def forgot_password_page():
    return FileResponse(BASE_DIR / "forgot_password.html")


@app.post("/forgot-password")
async def forgot_password(request: Request):
    data = await request.json()
    email = str(data.get("email", "")).strip().lower()
    user = get_user_by_email(email)
    if not user:
        return JSONResponse({"error": "Aucun compte avec cet email."}, status_code=404)
    token = make_reset_token(user["id"])
    base = str(request.base_url).rstrip("/")
    reset_url = f"{base}/reset-password?token={token}"
    sent = send_email(email, "Réinitialisation de votre mot de passe Répondly", f"Cliquez sur ce lien pour réinitialiser votre mot de passe :\n\n{reset_url}\n\nLien valable 1 heure.")
    if sent:
        return {"sent": True}
    return {"link": reset_url}


@app.get("/reset-password")
async def reset_password_page():
    return FileResponse(BASE_DIR / "reset_password.html")


@app.post("/reset-password")
async def reset_password(request: Request):
    data = await request.json()
    token = str(data.get("token", ""))
    password = str(data.get("password", ""))
    user_id = decode_reset_token(token)
    if not user_id:
        return JSONResponse({"error": "Lien invalide ou expiré."}, status_code=400)
    if len(password) < 6:
        return JSONResponse({"error": "Mot de passe trop court (minimum 6 caractères)."}, status_code=400)
    update_password(user_id, pwd_ctx.hash(password))
    return {"ok": True}


# ── Auth pages ──────────────────────────────────────────────────

@app.get("/register")
async def register_page():
    return FileResponse(BASE_DIR / "register.html")


@app.post("/register")
async def register(request: Request):
    form = await request.form()
    email = str(form.get("email", "")).strip().lower()
    password = str(form.get("password", ""))
    if not email or not password or len(password) < 6:
        return HTMLResponse("Email ou mot de passe invalide. <a href='/register'>Retour</a>", status_code=400)
    if get_user_by_email(email):
        return HTMLResponse("Email déjà utilisé. <a href='/login'>Se connecter</a>", status_code=400)
    bot_id = create_user(email, pwd_ctx.hash(password))
    verify_token = make_verify_token(bot_id)
    base = ""
    try:
        base = os.getenv("APP_URL", "").rstrip("/")
    except Exception:
        pass
    verify_url = f"{base}/verify-email?token={verify_token}"
    send_email(email, "Vérifiez votre email Répondly", f"Bienvenue sur Répondly !\n\nCliquez sur ce lien pour vérifier votre email :\n\n{verify_url}")
    token = make_token(bot_id)
    response = RedirectResponse("/dashboard", status_code=302)
    response.set_cookie("session", token, httponly=True, max_age=60 * 60 * 24 * 30)
    return response


@app.get("/login")
async def login_page():
    return FileResponse(BASE_DIR / "login.html")


@app.post("/login")
async def login(request: Request):
    form = await request.form()
    email = str(form.get("email", "")).strip().lower()
    password = str(form.get("password", ""))
    user = get_user_by_email(email)
    if not user or not pwd_ctx.verify(password, user["password_hash"]):
        return HTMLResponse("Email ou mot de passe incorrect. <a href='/login'>Retour</a>", status_code=401)
    token = make_token(user["id"])
    response = RedirectResponse("/dashboard", status_code=302)
    response.set_cookie("session", token, httponly=True, max_age=60 * 60 * 24 * 30)
    return response


@app.get("/logout")
async def logout():
    response = RedirectResponse("/login", status_code=302)
    response.delete_cookie("session")
    return response


# ── Protected pages ─────────────────────────────────────────────

@app.get("/dashboard")
async def dashboard(request: Request):
    if not get_current_user_id(request):
        return RedirectResponse("/login", status_code=302)
    return FileResponse(BASE_DIR / "dashboard.html")


@app.get("/admin")
async def admin_page(request: Request):
    if not get_current_user_id(request):
        return RedirectResponse("/login", status_code=302)
    return FileResponse(BASE_DIR / "admin.html")


@app.get("/admin/data")
async def admin_data(request: Request):
    user_id = get_current_user_id(request)
    if not user_id:
        return RedirectResponse("/login", status_code=302)
    config = load_config(user_id)
    knowledge = load_user_knowledge(user_id)
    return {"config": config, "knowledge": knowledge}


@app.post("/admin/save")
async def admin_save(request: Request):
    user_id = get_current_user_id(request)
    if not user_id:
        return RedirectResponse("/login", status_code=302)
    data = await request.json()
    save_config(user_id, {
        "bot_name": data.get("bot_name", ""),
        "bot_business": data.get("bot_business", ""),
        "bot_language": data.get("bot_language", "français"),
        "accent_color": data.get("accent_color", "#c9a84c"),
    })
    save_knowledge(user_id, data.get("knowledge", {}))
    return {"ok": True}


# ── Stripe ──────────────────────────────────────────────────────

@app.get("/subscribe")
async def subscribe(request: Request):
    user_id = get_current_user_id(request)
    if not user_id:
        return RedirectResponse("/login", status_code=302)
    user = get_user_by_id(user_id)
    base = str(request.base_url).rstrip("/")
    session = stripe.checkout.Session.create(
        customer_email=user["email"],
        payment_method_types=["card"],
        line_items=[{"price": os.getenv("STRIPE_PRICE_ID"), "quantity": 1}],
        mode="subscription",
        subscription_data={"trial_period_days": 14},
        success_url=f"{base}/dashboard?subscribed=1",
        cancel_url=f"{base}/dashboard",
        metadata={"user_id": user_id},
    )
    return RedirectResponse(session.url, status_code=302)


@app.post("/stripe-webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    try:
        if webhook_secret:
            event = stripe.Webhook.construct_event(payload, sig, webhook_secret)
        else:
            event = stripe.Event.construct_from(
                __import__("json").loads(payload), stripe.api_key
            )
    except Exception:
        return JSONResponse({"error": "invalid"}, status_code=400)

    etype = event["type"]
    obj   = event["data"]["object"]

    if etype == "checkout.session.completed":
        user_id = obj.get("metadata", {}).get("user_id")
        if user_id:
            update_subscription(user_id, "active", obj.get("customer"))

    elif etype in ("customer.subscription.deleted",):
        user = get_user_by_customer_id(obj.get("customer"))
        if user:
            update_subscription(user["id"], "canceled")

    elif etype == "invoice.payment_failed":
        user = get_user_by_customer_id(obj.get("customer"))
        if user:
            update_subscription(user["id"], "past_due")

    elif etype == "invoice.paid":
        user = get_user_by_customer_id(obj.get("customer"))
        if user:
            update_subscription(user["id"], "active")

    return {"ok": True}


# ── Public API ──────────────────────────────────────────────────

@app.get("/bot-config")
async def bot_config(id: str = Query(...)):
    config = load_config(id)
    return {"bot_name": config.get("bot_name", "Assistant"), "bot_language": config.get("bot_language", "français"), "accent_color": config.get("accent_color", "#c9a84c")}


class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []


def _user_can_use(user_id: str) -> bool:
    user = get_user_by_id(user_id)
    if not user:
        return False
    if user["subscription_status"] == "active":
        return True
    from datetime import datetime, timezone
    try:
        created_dt = datetime.fromisoformat((user["created_at"] or "").replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - created_dt).days < 14
    except Exception:
        return True


@app.post("/chat")
async def chat(req: ChatRequest, id: str = Query(...)):
    if not _check_rate_limit(id):
        return JSONResponse({"reply": "Trop de messages. Réessayez dans quelques minutes."}, status_code=429)
    if not _user_can_use(id):
        return JSONResponse({"reply": "Ce bot n'est plus actif. Abonnement requis."}, status_code=402)
    config = load_config(id)
    knowledge = load_knowledge(id)

    system = SYSTEM_PROMPT_TEMPLATE.format(
        bot_name=config["bot_name"],
        bot_business=config["bot_business"],
        language=config["bot_language"],
        knowledge=knowledge,
    )

    messages = [{"role": "system", "content": system}]
    for turn in req.history[-6:]:
        messages.append(turn)
    messages.append({"role": "user", "content": req.message})

    response = client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        messages=messages,
        temperature=float(os.getenv("BOT_TEMPERATURE", "0.4")),
        max_tokens=int(os.getenv("BOT_MAX_TOKENS", "300")),
    )
    increment_conversations(id)
    return {"reply": response.choices[0].message.content.strip()}


# ── Dashboard API ────────────────────────────────────────────────

@app.get("/me")
async def me(request: Request):
    user_id = get_current_user_id(request)
    if not user_id:
        return JSONResponse({"error": "unauthenticated"}, status_code=401)
    user = get_user_by_id(user_id)
    config = load_config(user_id)
    knowledge_exists = bool(load_user_knowledge(user_id))

    from datetime import datetime, timezone
    created = user["created_at"] or ""
    trial_active = True
    try:
        created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
        days_since = (datetime.now(timezone.utc) - created_dt).days
        trial_active = days_since < 14
    except Exception:
        pass

    sub_status = user["subscription_status"] or "trial"
    can_use = sub_status == "active" or trial_active

    return {
        "id": user_id,
        "email": user["email"],
        "email_verified": user.get("email_verified", False),
        "bot_configured": knowledge_exists,
        "bot_name": config.get("bot_name", ""),
        "subscription_status": sub_status,
        "trial_active": trial_active,
        "can_use": can_use,
        "total_conversations": user.get("total_conversations", 0),
    }


# ── Static (must be last) ────────────────────────────────────────

app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")

if __name__ == "__main__":
    init_db()
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=True)
