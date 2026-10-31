# 🚀 UniSearch AI Assistant & API

A dual-engine real-time AI search and web-scraping service powered by **Google Gemini**, **Firecrawl**, and **ZenRows** (with automatic zero-downtime credit failover).

Includes both a **Gradio Web Interface** (`app.py`) and a production-ready **Flask REST API** (`api.py`) with full CORS support.

---

## 📦 Features

- 🧠 **Gemini Models:** Supports `gemini-3.5-flash-lite`, `gemini-3.5-flash`, and `gemini-2.5-flash` with automatic retry/failover.
- ⚡ **Dual Scraping Engines:** Uses **Firecrawl** as the primary scraper, with automatic seamless failover to **ZenRows** if Firecrawl credits run out or rate limits are hit.
- 🌐 **Real-time Web Grounding:** Search the live web and scrape recent information for questions that require up-to-date information.
- 🔗 **Direct URL Scraping:** Scrapes any webpage to clean Markdown and generates summaries or answers questions about the content.
- 🔄 **CORS Enabled:** Call the API directly from React, Next.js, Vue, Flutter, iOS/Android apps, or backend servers.

---

## 🛠️ Setup & Running

### 1. Configure `.env`
Ensure your API keys are defined in your `.env` file:
```env
GEMINI_API_KEY=your_gemini_api_key
FIRECRAWL_API_KEY=your_firecrawl_api_key
ZENROWS_API_KEY=your_zenrows_api_key
PORT=5000
```

### 2. Run the Flask REST API
```bash
# Windows
.\venv\Scripts\python.exe api.py

# Linux / macOS
python api.py
```
API starts at: `http://localhost:5000`

### 3. Run the Gradio Web UI (Optional)
```bash
.\venv\Scripts\python.exe app.py
```
Web UI opens at: `http://127.0.0.1:7860`

---

## 📡 API Documentation

### 1. Health & Status
Check service health and active engines.
- **Method:** `GET`
- **Endpoint:** `/health` or `/`
- **Response:**
```json
{
  "status": "healthy",
  "service": "UniSearch AI API",
  "version": "1.0.0",
  "engines": {
    "gemini": true,
    "firecrawl_primary": true,
    "zenrows_fallback": true
  },
  "default_model": "gemini-3.5-flash-lite",
  "available_models": [
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-2.5-flash"
  ]
}
```

---

### 2. Chat & Real-Time Q&A
Ask real-time questions, converse with conversation memory, or scrape URLs passed in chat.
- **Method:** `POST`
- **Endpoint:** `/api/chat`
- **Headers:** `Content-Type: application/json`
- **Request Body:**
```json
{
  "message": "sabarimala today crowd",
  "history": [
    {"role": "user", "content": "Hello"},
    {"role": "assistant", "content": "Hi! How can I help you today?"}
  ],
  "website_context": "",
  "live_search": true,
  "model": "gemini-3.5-flash-lite"
}
```
- **Response (200 OK):**
```json
{
  "success": true,
  "response": "To check the live crowd status and queue wait times for Sabarimala today...",
  "engine_used": "ZenRows",
  "sources": [
    {
      "title": "Swami Sharanam Live Pilgrim Status",
      "url": "https://swamisharanam.in/en/live-status"
    }
  ],
  "history": [
    {"role": "user", "content": "sabarimala today crowd"},
    {"role": "assistant", "content": "..."}
  ],
  "website_context": "",
  "model_used": "gemini-3.5-flash-lite"
}
```

---

### 3. Direct URL Scraping
Scrapes a webpage, extracts clean Markdown, and optionally generates an AI bullet summary.
- **Method:** `POST`
- **Endpoint:** `/api/scrape`
- **Headers:** `Content-Type: application/json`
- **Request Body:**
```json
{
  "url": "https://news.ycombinator.com",
  "summarize": true,
  "model": "gemini-3.5-flash-lite"
}
```
- **Response (200 OK):**
```json
{
  "success": true,
  "url": "https://news.ycombinator.com",
  "engine_used": "ZenRows",
  "markdown": "# Hacker News\n\n1. [Title](https://...)...",
  "summary": "- Key story 1\n- Key story 2"
}
```

---

### 4. Direct Web Search & Scraping
Search the web and retrieve scraped markdown snippets directly.
- **Method:** `POST`
- **Endpoint:** `/api/search`
- **Headers:** `Content-Type: application/json`
- **Request Body:**
```json
{
  "query": "latest AI developments today",
  "limit": 3
}
```
- **Response (200 OK):**
```json
{
  "success": true,
  "query": "latest AI developments today",
  "engine_used": "Firecrawl",
  "count": 3,
  "sources": [
    {"title": "AI News Article", "url": "https://example.com/ai"}
  ],
  "snippets": [
    "Source: AI News Article (https://example.com/ai)\nContent:\n..."
  ]
}
```

---

## 💻 Integration Code Examples

### JavaScript / TypeScript (Fetch)
```javascript
const response = await fetch("http://localhost:5000/api/chat", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    message: "What is the crowd condition at Sabarimala today?",
    live_search: true
  })
});

const data = await response.json();
console.log(data.response);
console.log("Sources:", data.sources);
```

### Python (Requests)
```python
import requests

payload = {
    "message": "sabarimala today crowd",
    "live_search": True,
    "model": "gemini-3.5-flash-lite"
}

res = requests.post("http://localhost:5000/api/chat", json=payload)
data = res.json()
print("AI Response:", data["response"])
print("Engine Used:", data["engine_used"])
```

### cURL
```bash
curl -X POST http://localhost:5000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "sabarimala today crowd", "live_search": true}'
```

