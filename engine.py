import os
import sys
import re
import datetime
import urllib.parse
import requests
from dotenv import load_dotenv

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

# Load environment
load_dotenv()

from google import genai
try:
    from firecrawl import Firecrawl
except ImportError:
    from firecrawl import FirecrawlApp as Firecrawl

DEFAULT_MODEL = "gemini-3.5-flash-lite"

# Lazy-loaded clients
_gemini_client = None
_firecrawl_client = None

def get_gemini_client():
    global _gemini_client
    if _gemini_client is None:
        key = os.getenv("GEMINI_API_KEY")
        if key:
            _gemini_client = genai.Client(api_key=key)
    return _gemini_client

def get_firecrawl_client():
    global _firecrawl_client
    if _firecrawl_client is None:
        key = os.getenv("FIRECRAWL_API_KEY")
        if key and key != "your_firecrawl_api_key_here":
            try:
                _firecrawl_client = Firecrawl(api_key=key)
            except Exception:
                try:
                    from firecrawl import FirecrawlApp
                    _firecrawl_client = FirecrawlApp(api_key=key)
                except Exception as e:
                    print(f"Failed to initialize Firecrawl client: {e}")
    return _firecrawl_client

def clean_model_name(name):
    """
    Normalizes human-entered model names like 'Gemini 3.1 Flash Lite'
    into valid Gemini API identifiers like 'gemini-3.1-flash-lite'.
    """
    if not name:
        return DEFAULT_MODEL
    clean = str(name).strip()
    if clean.startswith("models/"):
        clean = clean[len("models/"):]
    clean = re.sub(r'[\s_]+', '-', clean).lower()
    return clean

def generate_with_fallback(prompt, model_name=DEFAULT_MODEL):
    """Generates content via Gemini with automatic fallback across flash models."""
    g_client = get_gemini_client()
    if not g_client:
        raise ValueError("GEMINI_API_KEY is not set or invalid.")

    target_model = clean_model_name(model_name)
    models_to_try = [target_model]
    for fallback in ["gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-2.5-flash"]:
        if fallback not in models_to_try:
            models_to_try.append(fallback)

    last_error = None
    for m in models_to_try:
        try:
            resp = g_client.models.generate_content(model=m, contents=prompt)
            return resp.text or "", m
        except Exception as err:
            last_error = err
            err_str = str(err)
            if "503" in err_str or "RESOURCE_EXHAUSTED" in err_str or "429" in err_str or "unexpected model name format" in err_str:
                print(f"⚠️ Model '{m}' notice: {err_str[:120]}. Trying fallback...")
            else:
                break
    raise last_error

def scrape_with_zenrows(url):
    """Fallback scraper using ZenRows API."""
    key = os.getenv("ZENROWS_API_KEY")
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
    except Exception as e:
        print(f"ZenRows scraping error: {e}")
    return None

def search_with_zenrows(query):
    """Fallback search using Bing via ZenRows when Firecrawl search limit is reached."""
    key = os.getenv("ZENROWS_API_KEY")
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
    """Detect if text contains a web URL."""
    url_match = re.search(r'https?://[^\s]+', str(text).strip())
    return url_match.group(0) if url_match else None

def normalize_history(raw_history):
    """
    Ensures every item in history strictly conforms to Gradio/API messages schema:
    [{'role': 'user'|'assistant', 'content': str}]
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

def scrape_url(url):
    """
    Scrapes a URL returning markdown and the engine used (Firecrawl -> ZenRows).
    Returns (content, engine_used).
    """
    fc_client = get_firecrawl_client()
    content = None
    engine_used = "Firecrawl"

    # 1. Firecrawl attempt
    if fc_client:
        try:
            print(f"🌐 [Firecrawl] Scraping URL: {url}")
            if hasattr(fc_client, "scrape"):
                result = fc_client.scrape(url, formats=["markdown"])
            elif hasattr(fc_client, "scrape_url"):
                result = fc_client.scrape_url(url, params={"formats": ["markdown"]})
            else:
                result = None
            content = getattr(result, "markdown", None)
            if not content and isinstance(result, dict):
                content = result.get("markdown")
        except Exception as fc_err:
            print(f"⚠️ Firecrawl scrape notice ({fc_err}). Switching to ZenRows fallback...")

    # 2. ZenRows fallback
    if not content:
        content = scrape_with_zenrows(url)
        if content:
            engine_used = "ZenRows"

    return content, engine_used if content else "None"

def search_web(query, limit=3):
    """
    Searches and scrapes live web data.
    Returns (scraped_snippets, sources, engine_used).
    """
    fc_client = get_firecrawl_client()
    scraped_snippets = []
    sources = []
    engine_used = "Firecrawl"

    # 1. Firecrawl search
    if fc_client:
        try:
            print(f"🔍 [Firecrawl] Searching live web for: {query}")
            search_res = fc_client.search(query, limit=limit, scrape_options={"formats": ["markdown"]})
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
                            sources.append({"title": title, "url": url})
        except Exception as search_err:
            print(f"⚠️ Firecrawl search notice ({search_err}). Attempting ZenRows fallback...")

    # 2. ZenRows search fallback
    if not scraped_snippets:
        zr_results = search_with_zenrows(query)
        if zr_results:
            engine_used = "ZenRows"
            for item in zr_results:
                scraped_snippets.append(f"Source: {item['title']} ({item['url']})\nContent:\n{item['content']}")
                sources.append({"title": item["title"], "url": item["url"]})

    return scraped_snippets, sources, engine_used if scraped_snippets else "None"

def process_chat(message, history=None, website_context="", live_search_enabled=True, model=DEFAULT_MODEL):
    """
    Main orchestration function for chat requests.
    Returns a dict with all details.
    """
    message = str(message).strip()
    if not message:
        return {
            "success": False,
            "error": "Empty message",
            "response": "",
            "history": history or [],
            "website_context": website_context
        }

    history = normalize_history(history)
    detected_url = extract_url(message)
    today_str = datetime.datetime.now().strftime("%B %d, %Y")
    engine_used = "None"
    sources = []

    # A. DIRECT URL SCRAPING
    if detected_url:
        content, engine_used = scrape_url(detected_url)
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
            ai_text, used_model = generate_with_fallback(prompt, model)
            response_text = f"✅ **Website scraped successfully!** (⚡ Scraped with **{engine_used}** | `{detected_url}`)\n\n" + ai_text
            sources.append({"title": detected_url, "url": detected_url})

    # B. REAL-TIME SEARCH / EXISTING CONTEXT
    else:
        conversation = ""
        for msg in history[-10:]:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            conversation += f"\n{role.capitalize()}: {content}"

        # Case 1: Q&A over previous website context (when live search is explicitly false)
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
            response_text, used_model = generate_with_fallback(prompt, model)

        # Case 2: Live Search enabled
        elif live_search_enabled:
            snippets, sources, engine_used = search_web(message, limit=3)
            if snippets:
                live_context = "\n\n---\n\n".join(snippets)
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
                ai_text, used_model = generate_with_fallback(prompt, model)
                source_links = [f"[{s['title']}]({s['url']})" if s['url'] else s['title'] for s in sources]
                source_footer = f"\n\n**🌐 Live Sources Scraped (via {engine_used}):**\n" + "\n".join(f"- {s}" for s in source_links) if source_links else ""
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
                response_text, used_model = generate_with_fallback(prompt, model)

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
            response_text, used_model = generate_with_fallback(prompt, model)

    history.append({"role": "user", "content": message})
    history.append({"role": "assistant", "content": response_text})

    return {
        "success": True,
        "response": response_text,
        "history": history,
        "website_context": website_context,
        "engine_used": engine_used,
        "sources": sources,
        "model_used": model
    }

