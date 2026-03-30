#!/usr/bin/env python3
"""
Paywall Bypass Tool - Intenta acceder a contenido de pago usando métodos alternativos.
"""

import urllib.parse
from flask import Flask, render_template, request, jsonify
import requests
from bs4 import BeautifulSoup

app = Flask(__name__)

GOOGLEBOT = {
    "User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

DESKTOP = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9",
    "Referer": "https://www.google.es/",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "cross-site",
}

MOBILE = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 "
                  "(KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9",
    "Referer": "https://www.google.es/",
}


def has_paywall(soup: BeautifulSoup) -> bool:
    """Detecta si la página tiene paywall activo (contenido bloqueado)."""
    indicators = [
        "[class*='paywall']", "[id*='paywall']",
        "[class*='suscri']", "[class*='subscri']",
        "[class*='premium']", "[class*='locked']",
        "[class*='blur']", "[class*='truncat']",
    ]
    for sel in indicators:
        if soup.select(sel):
            return True
    text = soup.get_text().lower()
    for kw in ["quiero el informe", "suscríbete", "hazte suscriptor",
                "acceso exclusivo", "contenido exclusivo para suscriptores"]:
        if kw in text:
            return True
    return False


def extract_hidden_content(soup: BeautifulSoup) -> str | None:
    """Intenta extraer contenido oculto por CSS (blur, display:none, etc.)."""
    # Buscar elementos con estilo que ocultan/difuminan contenido
    hidden_selectors = [
        "[style*='blur']", "[style*='overflow: hidden']",
        "[style*='max-height']", "[style*='clip']",
    ]
    texts = []
    for sel in hidden_selectors:
        for el in soup.select(sel):
            t = el.get_text(strip=True)
            if len(t) > 200:
                texts.append(t)
    return "\n\n".join(texts) if texts else None


def clean_html(html: str, base_url: str, aggressive: bool = False) -> str:
    """Extrae el contenido principal eliminando overlays y paywalls."""
    soup = BeautifulSoup(html, "html.parser")

    # Intentar rescatar contenido oculto por CSS antes de eliminar nada
    hidden = extract_hidden_content(soup)

    # Eliminar overlays/modales de suscripción
    remove_selectors = [
        ".paywall", ".paywalled", ".paywall-overlay", ".paywall-modal",
        ".subscription-wall", ".subscribe-wall", ".premium-overlay",
        ".modal-overlay", ".cookie-overlay", ".modal-backdrop",
        "[id*='paywall']", "[id*='overlay']", "[id*='modal']",
        ".newsletter-popup", ".newsletter-overlay",
        "nav", "footer", ".footer", ".header", "header",
    ]
    if aggressive:
        remove_selectors += ["aside", ".aside", ".sidebar", ".ad", ".ads", "[class*='banner']"]

    for selector in remove_selectors:
        for el in soup.select(selector):
            el.decompose()

    # Intentar extraer el artículo principal
    content_selectors = [
        "article", ".article-body", ".article-content", ".article__body",
        ".entry-content", ".post-content", ".content-body",
        ".news-body", ".informe-content", ".report-content",
        ".informe", ".noticia", ".texto", ".body",
        "main", ".main-content", "#main-content", "#content",
        ".story-body", ".body-text", ".text-content",
    ]

    content = None
    for selector in content_selectors:
        found = soup.select_one(selector)
        if found and len(found.get_text(strip=True)) > 300:
            content = found
            break

    if not content:
        content = soup.body or soup

    # Convertir URLs relativas a absolutas
    parsed = urllib.parse.urlparse(base_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    for tag in content.find_all(["img", "a"]):
        for attr in ["href", "src"]:
            val = tag.get(attr, "")
            if val.startswith("/"):
                tag[attr] = base + val

    result = str(content)
    if hidden:
        result += f'<div style="margin-top:2rem;padding:1rem;background:#fffde7;border:1px solid #f9a825;border-radius:8px"><strong>Contenido adicional detectado:</strong><p>{hidden}</p></div>'
    return result


def _get(url: str, headers: dict, timeout: int = 15):
    try:
        r = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        if r.status_code == 200 and len(r.text) > 500:
            return r
    except requests.exceptions.RequestException:
        pass
    return None


def _is_full_content(html: str) -> bool:
    """Verifica que el HTML tiene contenido sustancial (no solo preview)."""
    soup = BeautifulSoup(html, "html.parser")
    if has_paywall(soup):
        return False
    text = soup.get_text(strip=True)
    return len(text) > 2000


def try_googlebot(url: str) -> dict:
    r = _get(url, GOOGLEBOT)
    if r and _is_full_content(r.text):
        return {"success": True, "html": r.text, "source": "Googlebot UA"}
    return {"success": False}


def try_desktop_google_referer(url: str) -> dict:
    r = _get(url, DESKTOP)
    if r and _is_full_content(r.text):
        return {"success": True, "html": r.text, "source": "Desktop + Referer Google"}
    return {"success": False}


def try_mobile(url: str) -> dict:
    r = _get(url, MOBILE)
    if r and _is_full_content(r.text):
        return {"success": True, "html": r.text, "source": "Mobile UA"}
    return {"success": False}


def try_amp(url: str) -> dict:
    """Intenta versión AMP de la URL."""
    parsed = urllib.parse.urlparse(url)
    amp_urls = [
        url.rstrip("/") + "/amp",
        url.rstrip("/") + "?amp=1",
        f"{parsed.scheme}://amp.{parsed.netloc}{parsed.path}",
    ]
    for amp_url in amp_urls:
        r = _get(amp_url, GOOGLEBOT)
        if r and _is_full_content(r.text):
            return {"success": True, "html": r.text, "source": "Versión AMP", "archive_url": amp_url}
    return {"success": False}


def try_print_version(url: str) -> dict:
    """Intenta versión imprimible."""
    variants = [
        url + "?print=1", url + "?output=print",
        url + "/print", url + "?format=print",
    ]
    for v in variants:
        r = _get(v, DESKTOP)
        if r and _is_full_content(r.text):
            return {"success": True, "html": r.text, "source": "Versión imprimible", "archive_url": v}
    return {"success": False}


def try_archive_ph(url: str) -> dict:
    """Busca en archive.ph (archive.today)."""
    # archive.ph a veces redirige a la última versión archivada
    for base in ["https://archive.ph/newest/", "https://archive.today/newest/"]:
        r = _get(base + url, DESKTOP, timeout=20)
        if r and _is_full_content(r.text):
            return {"success": True, "html": r.text, "source": "archive.ph", "archive_url": base + url}
    return {"success": False}


def try_12ft(url: str) -> dict:
    proxy_url = f"https://12ft.io/proxy?q={urllib.parse.quote(url)}"
    r = _get(proxy_url, DESKTOP, timeout=20)
    if r and _is_full_content(r.text):
        return {"success": True, "html": r.text, "source": "12ft.io", "proxy_url": proxy_url}
    return {"success": False}


def try_google_cache(url: str) -> dict:
    cache_url = f"https://webcache.googleusercontent.com/search?q=cache:{urllib.parse.quote(url)}&hl=es"
    r = _get(cache_url, GOOGLEBOT)
    if r and _is_full_content(r.text):
        return {"success": True, "html": r.text, "source": "Google Cache", "cache_url": cache_url}
    return {"success": False}


def try_wayback_machine(url: str) -> dict:
    api = f"https://archive.org/wayback/available?url={urllib.parse.quote(url)}"
    r = _get(api, DESKTOP, timeout=10)
    if not r:
        return {"success": False}
    try:
        data = r.json()
        snapshot = data.get("archived_snapshots", {}).get("closest", {})
        if snapshot.get("available") and snapshot.get("url"):
            archive_url = snapshot["url"]
            r2 = _get(archive_url, DESKTOP, timeout=25)
            if r2 and _is_full_content(r2.text):
                return {
                    "success": True,
                    "html": r2.text,
                    "source": f"Wayback Machine ({snapshot.get('timestamp', '')[:8]})",
                    "archive_url": archive_url,
                }
    except Exception:
        pass
    return {"success": False}


def try_playwright(url: str) -> dict:
    """
    Navegador headless real con múltiples técnicas de bypass:
      1. Intercepta todas las llamadas de red (busca API de contenido)
      2. Manipula localStorage/sessionStorage/cookies para simular suscripción
      3. Elimina overlays y fuerza visibilidad del DOM
      4. Recarga tras manipulación para ver si el servidor responde diferente
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"success": False}

    api_responses = []
    all_requests = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=[
                "--no-sandbox", "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-web-security",
            ])
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                extra_http_headers={
                    "Referer": "https://www.google.es/",
                    "Accept-Language": "es-ES,es;q=0.9",
                },
                viewport={"width": 1280, "height": 900},
            )

            def handle_response(response):
                ct = response.headers.get("content-type", "")
                url_r = response.url
                all_requests.append({"url": url_r, "status": response.status})
                if "json" in ct or ("text" in ct and response.status == 200):
                    try:
                        body = response.body()
                        if len(body) > 800:
                            api_responses.append({
                                "url": url_r,
                                "status": response.status,
                                "ct": ct,
                                "body": body.decode("utf-8", errors="ignore"),
                            })
                    except Exception:
                        pass

            page = context.new_page()
            page.on("response", handle_response)

            # --- CARGA INICIAL ---
            page.goto(url, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(2000)

            # --- PASO 1: Inspeccionar localStorage/sessionStorage del sitio ---
            storage_data = page.evaluate("""() => {
                const ls = {}, ss = {};
                for (let i = 0; i < localStorage.length; i++) {
                    const k = localStorage.key(i);
                    ls[k] = localStorage.getItem(k);
                }
                for (let i = 0; i < sessionStorage.length; i++) {
                    const k = sessionStorage.key(i);
                    ss[k] = sessionStorage.getItem(k);
                }
                return { localStorage: ls, sessionStorage: ss };
            }""")

            # --- PASO 2: Inyectar valores de suscripción en localStorage ---
            page.evaluate("""() => {
                // Claves comunes que los sitios usan para controlar el acceso
                const subscriptionKeys = {
                    'subscriber': 'true', 'isSubscriber': 'true',
                    'subscription': 'active', 'subscriptionStatus': 'active',
                    'userType': 'subscriber', 'user_type': 'premium',
                    'isPremium': 'true', 'premium': 'true',
                    'hasAccess': 'true', 'access': 'full',
                    'suscriptor': 'true', 'suscripcion': 'activa',
                    'logged': 'true', 'loggedIn': 'true',
                    'authenticated': 'true', 'auth': '1',
                    'role': 'subscriber', 'plan': 'premium',
                    'metered_paywall_counter': '0',
                    'article_count': '0', 'articlesRead': '0',
                    'piano_access': 'true',
                    'paywall_bypass': 'true',
                };
                Object.entries(subscriptionKeys).forEach(([k, v]) => {
                    try { localStorage.setItem(k, v); } catch(e) {}
                    try { sessionStorage.setItem(k, v); } catch(e) {}
                });
                // También en cookies
                Object.entries(subscriptionKeys).forEach(([k, v]) => {
                    document.cookie = `${k}=${v}; path=/; max-age=86400`;
                });
            }""")

            # --- PASO 3: Recargar para que el sitio lea los nuevos valores ---
            page.reload(wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(2000)

            # --- PASO 4: Manipulaciones DOM agresivas ---
            page.evaluate("""() => {
                const removeSelectors = [
                    '[class*="paywall"]', '[id*="paywall"]',
                    '[class*="modal"]', '[id*="modal"]',
                    '[class*="overlay"]', '[id*="overlay"]',
                    '[class*="suscri"]', '[class*="subscri"]',
                    '[class*="premium"]', '[class*="locked"]',
                    '[class*="cookie"]', '[class*="gate"]',
                    '[class*="wall"]', '[class*="block"]',
                    'dialog',
                ];
                removeSelectors.forEach(sel => {
                    try { document.querySelectorAll(sel).forEach(el => el.remove()); } catch(e) {}
                });

                // Forzar visibilidad
                document.querySelectorAll('*').forEach(el => {
                    try {
                        const s = window.getComputedStyle(el);
                        if (s.filter && s.filter.includes('blur'))    el.style.filter = 'none';
                        if (s.webkitMaskImage && s.webkitMaskImage !== 'none') el.style.webkitMaskImage = 'none';
                        if (s.maskImage && s.maskImage !== 'none')    el.style.maskImage = 'none';
                        if (s.overflow === 'hidden' && el.scrollHeight > 500) {
                            el.style.overflow = 'visible';
                            el.style.maxHeight = 'none';
                            el.style.height = 'auto';
                        }
                        if (s.display === 'none' && el.className && (
                            el.className.toString().includes('content') ||
                            el.className.toString().includes('texto') ||
                            el.className.toString().includes('body') ||
                            el.className.toString().includes('article')
                        )) {
                            el.style.display = 'block';
                        }
                    } catch(e) {}
                });
                document.body.style.overflow = 'visible';
            }""")

            page.wait_for_timeout(1000)
            html_after = page.content()

            # --- PASO 5: Buscar contenido en respuestas de API ---
            import json
            for resp in sorted(api_responses, key=lambda x: -len(x["body"])):
                body = resp["body"]
                # Buscar JSON con contenido de artículo
                if len(body) > 2000:
                    try:
                        data = json.loads(body)
                        flat = json.dumps(data, ensure_ascii=False)
                        # Señales de que esto es contenido del artículo
                        if any(k in flat.lower() for k in ["informe", "perfumeria", "higiene", "contenido", "texto", "html", "body"]):
                            if len(flat) > 3000:
                                return {
                                    "success": True,
                                    "html": f"""
                                        <div style='padding:1rem;background:#e8f5e9;border:2px solid #4caf50;border-radius:8px;margin-bottom:1rem'>
                                            <strong>Contenido obtenido via API:</strong> {resp['url'][:100]}
                                        </div>
                                        <pre style='white-space:pre-wrap;word-break:break-word'>{flat[:60000]}</pre>
                                    """,
                                    "source": f"API interceptada: {resp['url'][:60]}",
                                }
                    except Exception:
                        pass

            soup_after = BeautifulSoup(html_after, "html.parser")
            if _is_full_content(html_after):
                return {
                    "success": True,
                    "html": html_after,
                    "source": "Headless + localStorage bypass",
                }

            # --- PASO 6: Devolver diagnóstico detallado ---
            api_log = "\n".join([
                f"• [{r['status']}] {r['url'][:120]}"
                for r in all_requests[-30:]
            ])
            storage_info = f"localStorage: {list(storage_data.get('localStorage', {}).keys())}"

            # Construir informe de debug + preview limpio
            debug_html = f"""
            <div style='background:#1e293b;color:#94a3b8;padding:1rem;border-radius:8px;margin-bottom:1rem;font-size:0.8rem;font-family:monospace'>
                <strong style='color:#e2e8f0'>Diagnóstico del sitio</strong><br><br>
                <strong>Storage inicial:</strong> {storage_info}<br><br>
                <strong>Últimas peticiones de red ({len(all_requests)} total):</strong><br>
                <pre style='margin:0.5rem 0;overflow:auto'>{api_log}</pre>
            </div>
            """
            page_content = clean_html(html_after, url, aggressive=True)
            browser.close()
            return {
                "success": True,
                "html": debug_html + page_content,
                "source": "Headless (paywall server-side — diagnóstico incluido)",
                "partial": True,
            }

    except Exception as e:
        return {"success": False, "error": str(e)}


def try_partial(url: str) -> dict:
    """Último recurso: devuelve lo que hay aunque sea preview, limpiando bien el HTML."""
    for headers in [GOOGLEBOT, DESKTOP, MOBILE]:
        r = _get(url, headers)
        if r:
            return {"success": True, "html": r.text, "source": "Preview (contenido parcial)", "partial": True}
    return {"success": False}


METHODS = [
    ("googlebot",       try_googlebot),
    ("desktop",         try_desktop_google_referer),
    ("mobile",          try_mobile),
    ("amp",             try_amp),
    ("print",           try_print_version),
    ("archive_ph",      try_archive_ph),
    ("12ft",            try_12ft),
    ("google_cache",    try_google_cache),
    ("wayback",         try_wayback_machine),
    ("playwright",      try_playwright),
    ("partial",         try_partial),
]


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/bypass", methods=["POST"])
def bypass():
    url = request.json.get("url", "").strip()
    if not url:
        return jsonify({"error": "URL requerida"}), 400
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    tried = []
    for name, method in METHODS:
        result = method(url)
        result["method"] = name
        tried.append(name)
        if result.get("success"):
            aggressive = result.get("partial", False)
            result["content"] = clean_html(result.pop("html"), url, aggressive=aggressive)
            result["tried"] = tried
            return jsonify({"success": True, "result": result})

    alternatives = {
        "archive_ph":    f"https://archive.ph/{url}",
        "wayback":       f"https://web.archive.org/web/*/{url}",
        "12ft":          f"https://12ft.io/proxy?q={urllib.parse.quote(url)}",
        "google_cache":  f"https://webcache.googleusercontent.com/search?q=cache:{urllib.parse.quote(url)}",
    }
    return jsonify({"success": False, "alternatives": alternatives, "tried": tried})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
