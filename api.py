import os
import sys

# Ensure UTF-8 output encoding for Windows consoles
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

from engine import (
    process_chat,
    scrape_url,
    search_web,
    generate_with_fallback,
    clean_model_name,
    DEFAULT_MODEL
)

app = Flask(__name__)
# Enable Cross-Origin Resource Sharing for all origins and routes
CORS(app, resources={r"/*": {"origins": "*"}})

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>UniSearch AI Assistant & API</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: 'Inter', sans-serif; background: #0f172a; color: #f8fafc; min-height: 100vh; display: flex; flex-direction: column; }
    header { background: #1e293b; border-bottom: 1px solid #334155; padding: 1rem 2rem; display: flex; justify-content: space-between; align-items: center; }
    header h1 { font-size: 1.25rem; font-weight: 700; color: #38bdf8; display: flex; align-items: center; gap: 0.5rem; }
    .status-badge { font-size: 0.75rem; background: #065f46; color: #34d399; padding: 0.35rem 0.75rem; border-radius: 9999px; font-weight: 600; }
    main { flex: 1; max-width: 900px; width: 100%; margin: 1.5rem auto; display: flex; flex-direction: column; gap: 1rem; padding: 0 1rem; }
    .chat-box { flex: 1; min-height: 480px; max-height: 600px; background: #1e293b; border: 1px solid #334155; border-radius: 12px; padding: 1.25rem; overflow-y: auto; display: flex; flex-direction: column; gap: 1rem; }
    .message { max-width: 82%; padding: 0.85rem 1.15rem; border-radius: 12px; line-height: 1.55; font-size: 0.95rem; word-break: break-word; }
    .message.user { align-self: flex-end; background: #2563eb; color: #ffffff; border-bottom-right-radius: 2px; }
    .message.assistant { align-self: flex-start; background: #334155; color: #f1f5f9; border-bottom-left-radius: 2px; }
    .message pre { background: #0f172a; padding: 0.5rem; border-radius: 6px; overflow-x: auto; margin: 0.5rem 0; font-size: 0.85rem; }
    .message a { color: #38bdf8; text-decoration: underline; }
    .controls { background: #1e293b; border: 1px solid #334155; border-radius: 12px; padding: 1rem; display: flex; flex-direction: column; gap: 0.75rem; }
    .input-row { display: flex; gap: 0.5rem; }
    input[type="text"] { flex: 1; background: #0f172a; border: 1px solid #475569; color: #f8fafc; padding: 0.85rem 1rem; border-radius: 8px; font-size: 0.95rem; outline: none; }
    input[type="text"]:focus { border-color: #38bdf8; }
    button { background: #2563eb; color: #ffffff; border: none; padding: 0.85rem 1.5rem; border-radius: 8px; font-weight: 600; cursor: pointer; transition: 0.2s; }
    button:hover { background: #1d4ed8; }
    button:disabled { background: #475569; cursor: not-allowed; }
    .options-row { display: flex; justify-content: space-between; align-items: center; font-size: 0.85rem; color: #94a3b8; }
    .options-row label { display: flex; align-items: center; gap: 0.4rem; cursor: pointer; }
    select { background: #0f172a; border: 1px solid #475569; color: #f8fafc; padding: 0.35rem 0.6rem; border-radius: 6px; outline: none; }
    .api-info { background: #1e293b; border: 1px solid #334155; border-radius: 12px; padding: 1rem; font-size: 0.85rem; color: #94a3b8; }
    .api-info code { background: #0f172a; color: #38bdf8; padding: 0.2rem 0.4rem; border-radius: 4px; font-family: monospace; }
  </style>
</head>
<body>
  <header>
    <h1>🔥 UniSearch AI Assistant & API</h1>
    <div class="status-badge">● API Active</div>
  </header>

  <main>
    <div class="chat-box" id="chatBox">
      <div class="message assistant">
        👋 <strong>Welcome to UniSearch!</strong><br>
        Ask any live question (e.g. <em>"sabarimala today crowd"</em>), paste a URL to scrape, or call our REST API via <code>POST /api/chat</code>.
      </div>
    </div>

    <div class="controls">
      <div class="input-row">
        <input type="text" id="userInput" placeholder="Ask a real-time question or paste a website URL..." autocomplete="off">
        <button id="sendBtn" onclick="sendMessage()">Send</button>
      </div>
      <div class="options-row">
        <label>
          <input type="checkbox" id="liveSearchCheck" checked>
          🌐 Live Web Scraping (Firecrawl + ZenRows fallback)
        </label>
        <div>
          <label>
            Model:
            <select id="modelSelect">
              <option value="gemini-3.5-flash-lite" selected>gemini-3.5-flash-lite</option>
              <option value="gemini-3.5-flash">gemini-3.5-flash</option>
              <option value="gemini-2.5-flash">gemini-2.5-flash</option>
            </select>
          </label>
        </div>
      </div>
    </div>

    <div class="api-info">
      📡 <strong>API Endpoint for Postman / Your Projects:</strong> <code>POST /api/chat</code> with body: <code>{"message": "your question", "live_search": true}</code>
    </div>
  </main>

  <script>
    let chatHistory = [];
    const chatBox = document.getElementById('chatBox');
    const userInput = document.getElementById('userInput');
    const sendBtn = document.getElementById('sendBtn');
    const liveSearchCheck = document.getElementById('liveSearchCheck');
    const modelSelect = document.getElementById('modelSelect');

    userInput.addEventListener('keypress', function(e) {
      if (e.key === 'Enter') sendMessage();
    });

    function appendMessage(role, text) {
      const msgDiv = document.createElement('div');
      msgDiv.className = 'message ' + role;
      msgDiv.innerHTML = text.replace(/\\n/g, '<br>');
      chatBox.appendChild(msgDiv);
      chatBox.scrollTop = chatBox.scrollHeight;
    }

    async function sendMessage() {
      const text = userInput.value.trim();
      if (!text) return;

      appendMessage('user', text);
      userInput.value = '';
      userInput.disabled = true;
      sendBtn.disabled = true;

      const loadingMsg = document.createElement('div');
      loadingMsg.className = 'message assistant';
      loadingMsg.id = 'loadingMsg';
      loadingMsg.innerHTML = '🔍 <em>Searching and scraping live web...</em>';
      chatBox.appendChild(loadingMsg);
      chatBox.scrollTop = chatBox.scrollHeight;

      try {
        const res = await fetch('/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            message: text,
            history: chatHistory,
            live_search: liveSearchCheck.checked,
            model: modelSelect.value
          })
        });

        const data = await res.json();
        chatBox.removeChild(loadingMsg);

        if (data.success) {
          chatHistory = data.history || [];
          appendMessage('assistant', data.response);
        } else {
          appendMessage('assistant', '❌ Error: ' + (data.error || 'Failed to generate response.'));
        }
      } catch (err) {
        if (document.getElementById('loadingMsg')) chatBox.removeChild(loadingMsg);
        appendMessage('assistant', '❌ Network error: ' + err.message);
      } finally {
        userInput.disabled = false;
        sendBtn.disabled = false;
        userInput.focus();
      }
    }
  </script>
</body>
</html>
"""

@app.route("/", methods=["GET"])
def index():
    """Serves the Web Chat UI for browsers, or JSON health check for API clients."""
    accept = request.headers.get("Accept", "")
    if "text/html" in accept:
        return render_template_string(HTML_TEMPLATE)
    return health_check()

@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint with system status."""
    has_gemini = bool(os.getenv("GEMINI_API_KEY"))
    has_firecrawl = bool(os.getenv("FIRECRAWL_API_KEY"))
    has_zenrows = bool(os.getenv("ZENROWS_API_KEY"))

    return jsonify({
        "status": "healthy",
        "service": "UniSearch AI API",
        "version": "1.0.0",
        "engines": {
            "gemini": has_gemini,
            "firecrawl_primary": has_firecrawl,
            "zenrows_fallback": has_zenrows
        },
        "default_model": DEFAULT_MODEL,
        "available_models": [
            "gemini-3.5-flash-lite",
            "gemini-3.5-flash",
            "gemini-2.5-flash"
        ],
        "endpoints": {
            "chat": "POST /api/chat",
            "scrape": "POST /api/scrape",
            "search": "POST /api/search",
            "health": "GET /health"
        }
    }), 200

@app.route("/api/chat", methods=["POST"])
def chat_endpoint():
    """
    Main Chat & Question-Answering Endpoint.
    
    Request JSON:
    {
        "message": "sabarimala today crowd",
        "history": [],
        "website_context": "",
        "live_search": true,
        "model": "gemini-3.5-flash-lite"
    }
    """
    data = request.get_json(silent=True) or {}
    message = data.get("message")

    if not message or not str(message).strip():
        return jsonify({
            "success": False,
            "error": "The 'message' field is required."
        }), 400

    history = data.get("history", [])
    website_context = data.get("website_context", "")
    live_search = data.get("live_search", True)
    model = data.get("model", DEFAULT_MODEL)

    try:
        result = process_chat(
            message=message,
            history=history,
            website_context=website_context,
            live_search_enabled=live_search,
            model=model
        )
        return jsonify(result), 200
    except Exception as e:
        print(f"Error in /api/chat: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route("/api/scrape", methods=["POST"])
def scrape_endpoint():
    """
    Dedicated URL Scraping Endpoint.
    
    Request JSON:
    {
        "url": "https://example.com",
        "summarize": true,
        "model": "gemini-3.5-flash-lite"
    }
    """
    data = request.get_json(silent=True) or {}
    url = data.get("url")

    if not url or not str(url).strip():
        return jsonify({
            "success": False,
            "error": "The 'url' field is required."
        }), 400

    summarize = data.get("summarize", False)
    model = data.get("model", DEFAULT_MODEL)

    try:
        markdown, engine_used = scrape_url(url.strip())
        if not markdown:
            return jsonify({
                "success": False,
                "error": f"Failed to extract markdown from {url} with Firecrawl and ZenRows."
            }), 502

        summary = ""
        if summarize:
            prompt = f"""
            Summarize the following website content in simple bullet points:

            URL: {url}
            Content:
            {markdown[:25000]}
            """
            summary, _ = generate_with_fallback(prompt, model)

        return jsonify({
            "success": True,
            "url": url,
            "engine_used": engine_used,
            "markdown": markdown,
            "summary": summary
        }), 200
    except Exception as e:
        print(f"Error in /api/scrape: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route("/api/search", methods=["POST"])
def search_endpoint():
    """
    Dedicated Live Web Search & Scraping Endpoint.
    
    Request JSON:
    {
        "query": "latest news about SpaceX",
        "limit": 3
    }
    """
    data = request.get_json(silent=True) or {}
    query = data.get("query")

    if not query or not str(query).strip():
        return jsonify({
            "success": False,
            "error": "The 'query' field is required."
        }), 400

    limit = data.get("limit", 3)
    try:
        limit = int(limit)
    except (ValueError, TypeError):
        limit = 3

    try:
        snippets, sources, engine_used = search_web(query.strip(), limit=limit)
        return jsonify({
            "success": True,
            "query": query,
            "engine_used": engine_used,
            "count": len(snippets),
            "sources": sources,
            "snippets": snippets
        }), 200
    except Exception as e:
        print(f"Error in /api/search: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "False").lower() in ("true", "1")
    print(f"🚀 Starting UniSearch Flask API on http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=debug)
