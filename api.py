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

from flask import Flask, request, jsonify
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

@app.route("/", methods=["GET"])
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
        "history": [
            {"role": "user", "content": "..."},
            {"role": "assistant", "content": "..."}
        ],
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

