(function () {
  "use strict";

  // Read bot_id and API origin from this script's src
  const scriptEl = document.currentScript;
  const scriptSrc = scriptEl ? scriptEl.src : window.location.origin + "/widget.js";
  const scriptUrl = new URL(scriptSrc, window.location.href);
  const BOT_ID = scriptUrl.searchParams.get("id") || "";
  const API_ORIGIN = scriptUrl.origin;

  if (!BOT_ID) {
    console.warn("[Répondly] Missing ?id= in script src.");
    return;
  }

  let history = [];
  let isTyping = false;
  let botName = "Assistant";
  let accentColor = "#c9a84c";

  // Fetch bot public config (name, language) then build widget
  fetch(`${API_ORIGIN}/bot-config?id=${BOT_ID}`)
    .then((r) => r.json())
    .then((cfg) => {
      botName = cfg.bot_name || "Assistant";
      accentColor = cfg.accent_color || "#c9a84c";
      buildWidget();
    })
    .catch(() => buildWidget());

  function buildWidget() {
    const greeting =
      `Bonjour ! Je suis ${botName}. Comment puis-je vous aider ?`;

    // Toggle button
    const toggle = document.createElement("button");
    toggle.id = "rpy-toggle";
    toggle.setAttribute("aria-label", "Ouvrir le chat");
    toggle.innerHTML = `
      <svg class="icon-chat" width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
      </svg>
      <svg class="icon-close" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5" stroke-linecap="round">
        <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
      </svg>
      <span class="rpy-dot"></span>`;

    // Widget container
    const widget = document.createElement("div");
    widget.id = "rpy-widget";
    widget.setAttribute("role", "dialog");
    widget.innerHTML = `
      <div id="rpy-header">
        <div class="rpy-avatar">◆</div>
        <div class="rpy-info">
          <div class="rpy-name">${escHtml(botName)}</div>
          <div class="rpy-status">En ligne</div>
        </div>
      </div>
      <div id="rpy-messages" role="log" aria-live="polite"></div>
      <div id="rpy-input-area">
        <textarea id="rpy-input" placeholder="Votre message…" rows="1" aria-label="Message"></textarea>
        <button id="rpy-send" aria-label="Envoyer" disabled>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>
          </svg>
        </button>
      </div>
      <div id="rpy-brand">Propulsé par <a href="https://repondly.com" target="_blank">Répondly</a></div>`;

    // Styles
    const style = document.createElement("style");
    style.textContent = `
      #rpy-toggle {
        position: fixed; bottom: 24px; right: 24px; z-index: 99998;
        width: 58px; height: 58px; border-radius: 50%;
        background: #c9a84c; border: none; cursor: pointer;
        display: flex; align-items: center; justify-content: center;
        box-shadow: 0 6px 24px rgba(0,0,0,0.35);
        transition: transform 0.2s, box-shadow 0.2s;
      }
      #rpy-toggle:hover { transform: scale(1.06); box-shadow: 0 8px 30px rgba(0,0,0,0.4); }
      #rpy-toggle .icon-close { display: none; }
      #rpy-toggle.open .icon-chat { display: none; }
      #rpy-toggle.open .icon-close { display: block; }
      .rpy-dot {
        position: absolute; top: 8px; right: 8px;
        width: 10px; height: 10px; border-radius: 50%;
        background: #10b981; border: 2px solid #c9a84c;
        animation: rpyPulse 2s infinite;
      }
      @keyframes rpyPulse { 0%,100%{transform:scale(1)} 50%{transform:scale(1.3)} }

      #rpy-widget {
        position: fixed; bottom: 96px; right: 24px; z-index: 99997;
        width: 340px; max-height: 520px;
        background: #111120; border: 1px solid rgba(255,255,255,0.08);
        border-radius: 16px;
        box-shadow: 0 24px 60px rgba(0,0,0,0.5);
        display: flex; flex-direction: column;
        opacity: 0; transform: translateY(16px) scale(0.97);
        pointer-events: none;
        transition: opacity 0.22s, transform 0.22s;
        font-family: system-ui, -apple-system, sans-serif;
        overflow: hidden;
      }
      #rpy-widget.visible { opacity: 1; transform: none; pointer-events: all; }

      #rpy-header {
        background: #0d0d1a; padding: 1rem 1.1rem;
        display: flex; align-items: center; gap: 0.75rem;
        border-bottom: 1px solid rgba(255,255,255,0.06); flex-shrink: 0;
      }
      .rpy-avatar {
        width: 36px; height: 36px; border-radius: 50%;
        background: linear-gradient(135deg, #c9a84c, #7a5c1e);
        display: flex; align-items: center; justify-content: center;
        color: #07070f; font-size: 0.9rem; font-weight: 700; flex-shrink: 0;
      }
      .rpy-name { font-size: 0.88rem; font-weight: 600; color: #ede9df; }
      .rpy-status { font-size: 0.7rem; color: #10b981; display: flex; align-items: center; gap: 0.3rem; }
      .rpy-status::before { content:''; width:6px; height:6px; border-radius:50%; background:#10b981; display:inline-block; }

      #rpy-messages {
        flex: 1; overflow-y: auto; padding: 1rem;
        display: flex; flex-direction: column; gap: 0.75rem;
        scrollbar-width: thin; scrollbar-color: rgba(255,255,255,0.1) transparent;
      }
      .rpy-msg { display: flex; gap: 0.5rem; }
      .rpy-msg.user { justify-content: flex-end; }
      .rpy-bubble {
        max-width: 82%; padding: 0.6rem 0.9rem;
        border-radius: 12px; font-size: 0.85rem; line-height: 1.5; color: #ede9df;
      }
      .rpy-msg.bot .rpy-bubble { background: #1a1a2e; border-bottom-left-radius: 3px; }
      .rpy-msg.user .rpy-bubble { background: #c9a84c; color: #07070f; border-bottom-right-radius: 3px; font-weight: 500; }
      .rpy-typing { display: flex; gap: 4px; align-items: center; padding: 0.6rem 0.9rem; background: #1a1a2e; border-radius: 12px; border-bottom-left-radius: 3px; width: fit-content; }
      .rpy-typing span { width: 6px; height: 6px; border-radius: 50%; background: #7a7a90; animation: rpyBounce 1s infinite; }
      .rpy-typing span:nth-child(2) { animation-delay: 0.15s; }
      .rpy-typing span:nth-child(3) { animation-delay: 0.3s; }
      @keyframes rpyBounce { 0%,80%,100%{transform:translateY(0)} 40%{transform:translateY(-5px)} }

      #rpy-input-area {
        padding: 0.75rem; border-top: 1px solid rgba(255,255,255,0.06);
        display: flex; gap: 0.5rem; align-items: flex-end; flex-shrink: 0;
        background: #0d0d1a;
      }
      #rpy-input {
        flex: 1; background: #111120; border: 1px solid rgba(255,255,255,0.08);
        border-radius: 8px; padding: 0.55rem 0.75rem;
        font-size: 0.85rem; font-family: inherit; color: #ede9df;
        resize: none; max-height: 90px; line-height: 1.45; outline: none;
      }
      #rpy-input::placeholder { color: #7a7a90; }
      #rpy-input:focus { border-color: rgba(201,168,76,0.4); }
      #rpy-send {
        width: 36px; height: 36px; border-radius: 8px; flex-shrink: 0;
        background: #c9a84c; border: none; cursor: pointer;
        display: flex; align-items: center; justify-content: center;
        transition: background 0.2s, opacity 0.2s;
      }
      #rpy-send:disabled { opacity: 0.4; cursor: default; }
      #rpy-send:not(:disabled):hover { background: #e8c96a; }

      #rpy-brand {
        text-align: center; padding: 0.4rem;
        font-size: 0.68rem; color: rgba(255,255,255,0.2);
        background: #0d0d1a; border-top: 1px solid rgba(255,255,255,0.04);
      }
      #rpy-brand a { color: rgba(255,255,255,0.3); text-decoration: none; }

      @media (max-width: 400px) {
        #rpy-widget { right: 8px; left: 8px; width: auto; bottom: 88px; }
        #rpy-toggle { right: 16px; bottom: 16px; }
      }
    `;
    document.head.appendChild(style);
    const acStyle = document.createElement("style");
    acStyle.textContent = `
      #rpy-toggle { background: ${accentColor} !important; }
      #rpy-toggle:hover { background: ${accentColor} !important; filter: brightness(1.08); }
      .rpy-dot { border-color: ${accentColor} !important; }
      .rpy-avatar { background: ${accentColor} !important; }
      .rpy-msg.user .rpy-bubble { background: ${accentColor} !important; }
      #rpy-send { background: ${accentColor} !important; }
      #rpy-send:not(:disabled):hover { background: ${accentColor} !important; filter: brightness(1.12); }
      #rpy-input:focus { border-color: ${accentColor}40 !important; }
    `;
    document.head.appendChild(acStyle);
    document.body.appendChild(toggle);
    document.body.appendChild(widget);

    const input = widget.querySelector("#rpy-input");
    const sendBtn = widget.querySelector("#rpy-send");
    const messagesEl = widget.querySelector("#rpy-messages");

    input.addEventListener("input", () => {
      input.style.height = "auto";
      input.style.height = Math.min(input.scrollHeight, 90) + "px";
      sendBtn.disabled = !input.value.trim();
    });

    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        if (!sendBtn.disabled && !isTyping) triggerSend();
      }
    });

    sendBtn.addEventListener("click", triggerSend);

    toggle.addEventListener("click", () => {
      const isOpen = widget.classList.contains("visible");
      widget.classList.toggle("visible", !isOpen);
      toggle.classList.toggle("open", !isOpen);
      toggle.setAttribute("aria-expanded", String(!isOpen));
      if (!isOpen) {
        const dot = toggle.querySelector(".rpy-dot");
        if (dot) dot.remove();
        setTimeout(() => input.focus(), 200);
        if (messagesEl.children.length === 0) addBotMsg(greeting);
      }
    });

    function triggerSend() {
      const text = input.value.trim();
      if (!text || isTyping) return;
      input.value = "";
      input.style.height = "auto";
      sendBtn.disabled = true;
      sendMessage(text);
    }

    function addBotMsg(text) {
      const div = document.createElement("div");
      div.className = "rpy-msg bot";
      div.innerHTML = `<div class="rpy-bubble">${escHtml(text)}</div>`;
      messagesEl.appendChild(div);
      scrollBottom();
    }

    function addUserMsg(text) {
      const div = document.createElement("div");
      div.className = "rpy-msg user";
      div.innerHTML = `<div class="rpy-bubble">${escHtml(text)}</div>`;
      messagesEl.appendChild(div);
      scrollBottom();
    }

    function showTyping() {
      const div = document.createElement("div");
      div.className = "rpy-msg bot"; div.id = "rpy-typing";
      div.innerHTML = `<div class="rpy-typing"><span></span><span></span><span></span></div>`;
      messagesEl.appendChild(div);
      scrollBottom();
    }

    function hideTyping() {
      const el = document.getElementById("rpy-typing");
      if (el) el.remove();
    }

    async function sendMessage(text) {
      addUserMsg(text);
      isTyping = true; showTyping();
      try {
        const res = await fetch(`${API_ORIGIN}/chat?id=${BOT_ID}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: text, history }),
        });
        if (!res.ok) throw new Error(res.status);
        const data = await res.json();
        hideTyping(); addBotMsg(data.reply);
        history.push({ role: "user", content: text });
        history.push({ role: "assistant", content: data.reply });
        if (history.length > 12) history = history.slice(-12);
      } catch {
        hideTyping();
        addBotMsg("Une erreur s'est produite. Veuillez réessayer.");
      } finally {
        isTyping = false;
      }
    }

    function scrollBottom() {
      requestAnimationFrame(() => { messagesEl.scrollTop = messagesEl.scrollHeight; });
    }
  }

  function escHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;")
      .replace(/\n/g, "<br>");
  }
})();
