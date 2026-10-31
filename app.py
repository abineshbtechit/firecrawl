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
from dotenv import load_dotenv

load_dotenv()

from engine import (
    process_chat,
    DEFAULT_MODEL
)

def gradio_chatbot(message, history, website_context, live_search_enabled, selected_model):
    """Bridge function for the Gradio UI."""
    res = process_chat(
        message=message,
        history=history,
        website_context=website_context,
        live_search_enabled=live_search_enabled,
        model=selected_model
    )
    return res["history"], res["website_context"]

# GRADIO INTERFACE
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

if __name__ == "__main__":
    demo.launch(debug=True)
