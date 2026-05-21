# Aurore Paris — Chatbot Démo

Asset de vente pour prospecter des marques DTC.

## Lancement rapide

```bash
# 1. Cloner / se placer dans le dossier
cd chatbot-demo

# 2. Copier et remplir les variables d'environnement
cp .env.example .env
# → édite .env et colle ta clé OPENAI_API_KEY

# 3. Installer les dépendances
pip install -r requirements.txt

# 4. Lancer
python backend/main.py
```

Ouvrir **http://localhost:8000**

## Structure

```
chatbot-demo/
├── backend/
│   ├── main.py          # FastAPI : endpoint /chat + serveur fichiers statiques
│   └── knowledge.json   # Catalogue produits + livraison + retours + FAQ
├── frontend/
│   ├── index.html       # Faux site e-commerce (style Shopify)
│   ├── widget.js        # Widget chatbot flottant
│   └── widget.css       # Styles widget
├── requirements.txt
├── .env.example
└── README.md
```

## Fonctionnement du bot

- Modèle : `gpt-4o-mini`
- RAG simple : `knowledge.json` injecté dans le system prompt à chaque requête
- Historique conversationnel : 6 derniers tours conservés en mémoire côté client
- Hors scope → demande l'email pour transmission à l'équipe
- Langue : français uniquement, max 3 phrases par réponse
