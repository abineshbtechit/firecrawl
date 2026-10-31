import os
import sys
import re
import datetime
import urllib.parse
import requests

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
from google import genai
try:
    from firecrawl import Firecrawl
except ImportError:
    from firecrawl import FirecrawlApp as Firecrawl
from dotenv import load_dotenv

# 1. LOAD LOCAL ENVIRONMENT VARIABLES
load_dotenv()

gemini_key = os.getenv("GEMINI_API_KEY")
firecrawl_key = os.getenv("FIRECRAWL_API_KEY")
zenrows_key = os.getenv("ZENROWS_API_KEY")

if not gemini_key:
    print("⚠️ Notice: Ensure GEMINI_API_KEY is configured in .env")

# 2. INITIALIZE APIs
gemini = genai.Client(api_key=gemini_key) if gemini_key else None

def get_firecrawl_client(api_key):
    if not api_key:
        return None
    try:
        return Firecrawl(api_key=api_key)
    except Exception:
        try:
            from firecrawl import FirecrawlApp
            return FirecrawlApp(api_key=api_key)
        except Exception as e:
            print(f"Failed to initialize Firecrawl client: {e}")
            return None

firecrawl = get_firecrawl_client(firecrawl_key)
DEFAULT_MODEL = "gemini-3.5-flash-lite"

def clean_model_name(name):
    """
    Normalizes human-entered model names like 'Gemini 3.1 Flash Lite'
    into valid Gemini API identifiers like 'gemini-3.1-flash-lite'.
    """
    if not name:
        return DEFAULT_MODEL
    clean = name.strip()
    if clean.startswith("models/"):
        clean = clean[len("models/"):]
    # Convert spaces/underscores to hyphens and lowercase
    clean = re.sub(r'[\s_]+', '-', clean).lower()
    return clean

def generate_with_fallback(g_client, model_name, prompt):
    """Generates content with automatic fallback to another flash model if quota or busy."""
    target_model = clean_model_name(model_name)
    models_to_try = [target_model]
    for fallback in ["gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-2.5-flash"]:
        if fallback not in models_to_try:
            models_to_try.append(fallback)

    last_error = None
    for m in models_to_try:
        try:
            resp = g_client.models.generate_content(model=m, contents=prompt)
            return resp.text or ""
        except Exception as err:
            last_error = err
            err_str = str(err)
            # If unexpected model format, fail fast or try fallback
            if "unexpected model name format" in err_str:
                print(f"⚠️ Model format error for '{m}': {err}. Trying fallback...")
            elif "503" in err_str or "RESOURCE_EXHAUSTED" in err_str or "429" in err_str:
                print(f"⚠️ Model '{m}' is busy/quota exceeded. Trying fallback...")
            else:
                # Other non-retryable error
                break
    raise last_error

# Fallback Scrapers: ZenRows
def scrape_with_zenrows(url):
    """Fallback scraper using ZenRows API when Firecrawl is unavailable or limit reached."""
    key = os.getenv("ZENROWS_API_KEY") or zenrows_key
    if not key or key == "your_zenrows_api_key_here":
        return None
    try:
        print(f"⚡ [ZenRows Fallback] Scraping: {url}")
        params = {
            "apikey": key,
            "url": url,
            "js_render": "true",
            "markdown_response": "true"
        }
        resp = requests.get("https://api.zenrows.com/v1/", params=params, timeout=30)
        if resp.status_code == 200 and resp.text.strip():
            return resp.text.strip()
        else:
            print(f"ZenRows API response status {resp.status_code}: {resp.text[:100]}")
    except Exception as e:
        print(f"ZenRows fallback error: {e}")
    return None

def search_with_zenrows(query):
    """Fallback search using Bing via ZenRows when Firecrawl search limit is reached."""
    key = os.getenv("ZENROWS_API_KEY") or zenrows_key
    if not key or key == "your_zenrows_api_key_here":
        return []
    try:
        print(f"⚡ [ZenRows Fallback] Searching live web for: {query}")
        search_url = f"https://www.bing.com/search?q={urllib.parse.quote(query)}"
        params = {
            "apikey": key,
            "url": search_url,
            "js_render": "true",
            "markdown_response": "true"
        }
        resp = requests.get("https://api.zenrows.com/v1/", params=params, timeout=30)
        if resp.status_code == 200 and resp.text.strip():
            content = resp.text.strip()
            return [{
                "title": "Bing Live Web Results (via ZenRows)",
                "url": search_url,
                "content": content[:6000]
            }]
    except Exception as e:
        print(f"ZenRows search fallback error: {e}")
    return []

def extract_url(text):
    """Detect if a message contains a web URL."""
    url_match = re.search(r'https?://[^\s]+', text.strip())
    return url_match.group(0) if url_match else None

def normalize_history(raw_history):
    """
    Ensures every item in history strictly conforms to Gradio's messages schema:
    [{'role': 'user'|'assistant', 'content': str}]
    Handles legacy tuples [user_msg, bot_msg], dicts with complex content, and ChatMessage objects.
    """
    clean_history = []
    if not raw_history:
        return clean_history

    for item in raw_history:
        if isinstance(item, (list, tuple)):
            if len(item) >= 1 and item[0]:
                u_text = item[0] if isinstance(item[0], str) else str(item[0])
                clean_history.append({"role": "user", "content": u_text})
            if len(item) >= 2 and item[1]:
                b_text = item[1] if isinstance(item[1], str) else str(item[1])
                clean_history.append({"role": "assistant", "content": b_text})
        elif isinstance(item, dict):
            role = item.get("role", "user")
            content = item.get("content", "")
            if isinstance(content, list):
                extracted = []
                for sub in content:
                    if isinstance(sub, dict) and "text" in sub:
                        extracted.append(sub["text"])
                    elif isinstance(sub, str):
                        extracted.append(sub)
                content = "\n".join(extracted) if extracted else str(content)
            elif not isinstance(content, str):
                content = str(content) if content is not None else ""
            clean_history.append({"role": role, "content": content})
        elif hasattr(item, "role") and hasattr(item, "content"):
            r = getattr(item, "role")
            c = getattr(item, "content")
            if isinstance(c, list):
                extracted = [getattr(sub, "text", str(sub)) for sub in c]
                c = "\n".join(extracted)
            clean_history.append({"role": str(r), "content": str(c)})
    return clean_history

# 3. CHATBOT BACKEND
def chatbot(message, history, website_context, live_search_enabled, selected_model):
    history = normalize_history(history)
    message = message.strip()
    if not message:
        return history, website_context

    website_context = website_context or ""
    response_text = ""
    active_model = clean_model_name(selected_model or DEFAULT_MODEL)

    curr_gemini_key = os.getenv("GEMINI_API_KEY") or gemini_key
    curr_firecrawl_key = os.getenv("FIRECRAWL_API_KEY") or firecrawl_key
    curr_zenrows_key = os.getenv("ZENROWS_API_KEY") or zenrows_key
    g_client = gemini or (genai.Client(api_key=curr_gemini_key) if curr_gemini_key else None)
    fc_client = firecrawl or get_firecrawl_client(curr_firecrawl_key)

    if not g_client:
        response_text = "❌ Gemini API key is missing. Please set GEMINI_API_KEY in your .env file."
        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": response_text})
        return history, website_context

    detected_url = extract_url(message)
    today_str = datetime.datetime.now().strftime("%B %d, %Y")

    # A. DIRECT URL SCRAPING PIPELINE (Firecrawl -> ZenRows Fallback)
    if detected_url:
        try:
            content = None
            engine_used = "Firecrawl"

            # 1. Try Firecrawl
            if fc_client:
                try:
                    print(f"🌐 [Firecrawl] Scraping URL: {detected_url}")
                    if hasattr(fc_client, "scrape"):
                        result = fc_client.scrape(detected_url, formats=["markdown"])
                    elif hasattr(fc_client, "scrape_url"):
                        result = fc_client.scrape_url(detected_url, params={"formats": ["markdown"]})
                    else:
                        result = None
                    content = getattr(result, "markdown", None)
                    if not content and isinstance(result, dict):
                        content = result.get("markdown")
                except Exception as fc_err:
                    print(f"⚠️ Firecrawl scrape notice ({fc_err}). Attempting ZenRows fallback...")

            # 2. Fallback to ZenRows if Firecrawl failed or limit was reached
            if not content and curr_zenrows_key:
                content = scrape_with_zenrows(detected_url)
                if content:
                    engine_used = "ZenRows"

            if not content:
                response_text = f"⚠️ Could not extract markdown content from `{detected_url}` with either Firecrawl or ZenRows."
            else:
                website_context = content[:25000]
                prompt = f"""
                You are a helpful AI assistant.
                Today's date is: {today_str}.

                The user provided this website: {detected_url}
                Website Content:
                {website_context}

                Please:
                1. Summarize this website in clear, concise bullet points.
                2. Let the user know they can ask any follow-up questions about this website.
                """
                ai_text = generate_with_fallback(g_client, active_model, prompt)
                badge = f"⚡ Scraped with **{engine_used}**"
                response_text = f"✅ **Website scraped successfully!** ({badge} | `{detected_url}`)\n\n" + (ai_text or "Content extracted.")
        except Exception as e:
            response_text = f"❌ Website scraping failed: {str(e)}"

    # B. REAL-TIME WEB SEARCH & SCRAPING (Firecrawl -> ZenRows Fallback) OR Q&A OVER PREVIOUS WEBSITE
    else:
        try:
            conversation = ""
            for msg in history[-10:]:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                conversation += f"\n{role.capitalize()}: {content}"

            # Case 1: If user already scraped a website and unchecked live search, use existing website context
            if website_context and not live_search_enabled:
                prompt = f"""
                You are a helpful AI assistant.
                Today's date is: {today_str}.
                Answer the user's question using the previously scraped website content whenever relevant.
                
                IMPORTANT:
                - Do not invent facts.
                - If the answer is missing from the website, clearly say so.
                
                SCRAPED WEBSITE CONTENT:
                {website_context}
                
                PREVIOUS CONVERSATION:
                {conversation}
                
                USER QUESTION:
                {message}
                """
                response_text = generate_with_fallback(g_client, active_model, prompt) or "No response generated."

            # Case 2: Live Web Search & Scraping enabled
            elif live_search_enabled and (fc_client or curr_zenrows_key):
                scraped_snippets = []
                sources = []
                engine_used = "Firecrawl"

                # 1. Try Firecrawl search
                if fc_client:
                    try:
                        print(f"🔍 [Firecrawl] Searching & Scraping live web for: {message}")
                        search_res = fc_client.search(message, limit=3, scrape_options={"formats": ["markdown"]})
                        if hasattr(search_res, "web") and search_res.web:
                            for item in search_res.web:
                                title = getattr(item, "title", None) or "Web Source"
                                url = getattr(item, "url", None) or ""
                                desc = getattr(item, "description", None) or ""
                                md = getattr(item, "markdown", None) or ""
                                snippet = md[:3000] if md else desc
                                if snippet:
                                    scraped_snippets.append(f"Source: {title} ({url})\nContent:\n{snippet}")
                                    if url:
                                        sources.append(f"[{title}]({url})")
                    except Exception as search_err:
                        print(f"⚠️ Firecrawl search notice ({search_err}). Attempting ZenRows search fallback...")

                # 2. Fallback to ZenRows search if Firecrawl failed or limit was reached
                if not scraped_snippets and curr_zenrows_key:
                    zr_results = search_with_zenrows(message)
                    if zr_results:
                        engine_used = "ZenRows"
                        for item in zr_results:
                            scraped_snippets.append(f"Source: {item['title']} ({item['url']})\nContent:\n{item['content']}")
                            sources.append(f"[{item['title']}]({item['url']})")

                if scraped_snippets:
                    live_context = "\n\n---\n\n".join(scraped_snippets)
                    prompt = f"""
                    You are a helpful AI assistant.
                    Today's date is: {today_str}.

                    Answer the user's question using the live web scraped information below.
                    Provide an up-to-date, accurate, and direct response.
                    Cite the relevant sources in your response.

                    LIVE WEB SCRAPED INFORMATION:
                    {live_context}

                    PREVIOUS CONVERSATION:
                    {conversation}

                    USER QUESTION:
                    {message}
                    """
                    ai_text = generate_with_fallback(g_client, active_model, prompt)
                    source_footer = f"\n\n**🌐 Live Sources Scraped (via {engine_used}):**\n" + "\n".join(f"- {s}" for s in sources) if sources else ""
                    response_text = (ai_text or "No response generated.") + source_footer
                else:
                    prompt = f"""
                    You are a helpful AI assistant.
                    Today's date is: {today_str}.
                    Answer clearly with simple explanations.

                    PREVIOUS CONVERSATION:
                    {conversation}
                    
                    USER QUESTION:
                    {message}
                    """
                    response_text = generate_with_fallback(g_client, active_model, prompt) or "No response generated."

            # Case 3: Standard LLM chat
            else:
                prompt = f"""
                You are a helpful AI assistant.
                Today's date is: {today_str}.
                Answer clearly with simple explanations.

                PREVIOUS CONVERSATION:
                {conversation}
                
                USER QUESTION:
                {message}
                """
                response_text = generate_with_fallback(g_client, active_model, prompt) or "No response generated."

        except Exception as e:
            response_text = f"❌ Gemini error: {str(e)}"

    # C. APPEND AS DICTIONARIES FOR NATIVE GRADIO v5/v6 CHATBOT
    history.append({"role": "user", "content": message})
    history.append({"role": "assistant", "content": response_text})
    return history, website_context

# 4. GRADIO INTERFACE
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
        chatbot,
        inputs=[message, chat, website_context, live_search_toggle, model_dropdown],
        outputs=[chat, website_context]
    ).then(lambda: "", outputs=message)

    message.submit(
        chatbot,
        inputs=[message, chat, website_context, live_search_toggle, model_dropdown],
        outputs=[chat, website_context]
    ).then(lambda: "", outputs=message)

    clear.click(lambda: ([], ""), outputs=[chat, website_context])

if __name__ == "__main__":
    demo.launch(debug=True)
