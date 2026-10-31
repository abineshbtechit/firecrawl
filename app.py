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

import gradio as gr
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from dotenv import load_dotenv

load_dotenv()

from engine import (
    process_chat,
    scrape_url,
    search_web,
    generate_with_fallback,
    DEFAULT_MODEL
)

def gradio_chatbot(message, history, website_context, live_search_enabled, selected_model):
    res = process_chat(
        message=message,
        history=history,
        website_context=website_context,
        live_search_enabled=live_search_enabled,
        model=selected_model
    )
    return res["history"], res["website_context"]

# 1. BUILD GRADIO INTERFACE
with gr.Blocks(title="UniSearch AI Chat") as demo:
    gr.Markdown("# 🔥 UniSearch AI Assistant\n\nAsk real-time questions, scrape websites, or search the web with Gemini & multi-engine fallback (**Firecrawl + ZenRows**).")
    website_context = gr.State("")
    
    try:
        chat = gr.Chatbot(height=520, type="messages", value=[])
    except TypeError:
        chat = gr.Chatbot(height=520, value=[])

    with gr.Row():
        message = gr.Textbox(
            placeholder="Ask anything (e.g. 'sabarimala today crowd') or paste a website URL (e.g. 'https://...')...",
            label="Your Message",
            scale=7
        )
        model_dropdown = gr.Dropdown(
            choices=["gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-2.5-flash"],
            value=DEFAULT_MODEL,
            label="Gemini Model",
            scale=2
        )
        live_search_toggle = gr.Checkbox(
            value=True,
            label="🌐 Live Web Scraping",
            info="Firecrawl primary, ZenRows fallback",
            scale=2
        )

    with gr.Row():
        send = gr.Button("Send", variant="primary")
        clear = gr.Button("Clear Chat")

    send.click(
        gradio_chatbot,
        inputs=[message, chat, website_context, live_search_toggle, model_dropdown],
        outputs=[chat, website_context]
    ).then(lambda: "", outputs=message)

    message.submit(
        gradio_chatbot,
        inputs=[message, chat, website_context, live_search_toggle, model_dropdown],
        outputs=[chat, website_context]
    ).then(lambda: "", outputs=message)

    clear.click(lambda: ([], ""), outputs=[chat, website_context])

# 2. REST API ROUTES (For Postman, Mobile Apps, and Other Projects)
api = FastAPI(title="UniSearch AI API")
api.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@api.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "UniSearch AI API",
        "engines": {
            "gemini": bool(os.getenv("GEMINI_API_KEY")),
            "firecrawl_primary": bool(os.getenv("FIRECRAWL_API_KEY")),
            "zenrows_fallback": bool(os.getenv("ZENROWS_API_KEY"))
        },
        "default_model": DEFAULT_MODEL,
        "available_models": ["gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-2.5-flash"]
    }

@api.post("/api/chat")
async def chat_api(request: Request):
    try:
        data = await request.json()
    except Exception:
        data = {}
    message = data.get("message")
    if not message or not str(message).strip():
        return JSONResponse(status_code=400, content={"success": False, "error": "The 'message' field is required."})

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
        return result
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})

@api.post("/api/scrape")
async def scrape_api(request: Request):
    try:
        data = await request.json()
    except Exception:
        data = {}
    url = data.get("url")
    if not url:
        return JSONResponse(status_code=400, content={"success": False, "error": "The 'url' field is required."})

    summarize = data.get("summarize", False)
    model = data.get("model", DEFAULT_MODEL)
    try:
        markdown, engine_used = scrape_url(url.strip())
        summary = ""
        if summarize and markdown:
            prompt = f"Summarize in simple bullet points:\n\nURL: {url}\n\nContent:\n{markdown[:25000]}"
            summary, _ = generate_with_fallback(prompt, model)
        return {
            "success": bool(markdown),
            "url": url,
            "engine_used": engine_used,
            "markdown": markdown or "",
            "summary": summary
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})

@api.post("/api/search")
async def search_api(request: Request):
    try:
        data = await request.json()
    except Exception:
        data = {}
    query = data.get("query")
    if not query:
        return JSONResponse(status_code=400, content={"success": False, "error": "The 'query' field is required."})

    limit = data.get("limit", 3)
    try:
        snippets, sources, engine_used = search_web(query.strip(), limit=int(limit))
        return {
            "success": True,
            "query": query,
            "engine_used": engine_used,
            "sources": sources,
            "snippets": snippets
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})

# Mount Gradio UI at root '/' on top of the REST API
app = gr.mount_gradio_app(api, demo, path="/")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 7860))
    print(f"🚀 Running UniSearch (Web UI + REST API) on http://0.0.0.0:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
