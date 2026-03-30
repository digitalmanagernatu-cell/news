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
    Navegador headless real: carga la página, intercepta APIs, manipula DOM.
    Técnicas:
      1. Elimina overlays/paywalls del DOM con JS
      2. Desactiva event listeners que ocultan contenido
      3. Busca llamadas XHR/fetch que cargan el contenido
      4. Fuerza visibilidad de elementos ocultos
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"success": False}

    api_responses = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=[
                "--no-sandbox", "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
            ])
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                extra_http_headers={"Referer": "https://www.google.es/"},
                viewport={"width": 1280, "height": 900},
            )

            # Interceptar respuestas de red que puedan contener el artículo
            def handle_response(response):
                ct = response.headers.get("content-type", "")
                if "json" in ct or "text" in ct:
                    try:
                        body = response.body()
                        if len(body) > 1000:
                            api_responses.append({
                                "url": response.url,
                                "status": response.status,
                                "body": body.decode("utf-8", errors="ignore"),
                            })
                    except Exception:
                        pass

            page = context.new_page()
            page.on("response", handle_response)

            page.goto(url, wait_until="networkidle", timeout=30000)

            # Esperar a que cargue el contenido dinámico
            page.wait_for_timeout(3000)

            # Manipulaciones DOM para revelar contenido oculto
            page.evaluate("""() => {
                // Eliminar overlays y modales de pago
                const removeSelectors = [
                    '[class*="paywall"]', '[id*="paywall"]',
                    '[class*="modal"]', '[id*="modal"]',
                    '[class*="overlay"]', '[id*="overlay"]',
                    '[class*="suscri"]', '[class*="subscri"]',
                    '[class*="premium"]', '[class*="locked"]',
                    '[class*="cookie"]', '[class*="banner"]',
                    'dialog', '.backdrop',
                ];
                removeSelectors.forEach(sel => {
                    document.querySelectorAll(sel).forEach(el => el.remove());
                });

                // Forzar visibilidad de todo el contenido
                document.querySelectorAll('*').forEach(el => {
                    const style = window.getComputedStyle(el);
                    if (style.filter && style.filter.includes('blur')) {
                        el.style.filter = 'none';
                    }
                    if (style.overflow === 'hidden' && el.scrollHeight > 300) {
                        el.style.overflow = 'visible';
                        el.style.maxHeight = 'none';
                    }
                    if (style.webkitMaskImage || style.maskImage) {
                        el.style.webkitMaskImage = 'none';
                        el.style.maskImage = 'none';
                    }
                });

                // Desactivar bloqueo de scroll/selección
                document.body.style.overflow = 'auto';
                document.documentElement.style.overflow = 'auto';
                document.body.onscroll = null;
                window.onscroll = null;
            }""")

            page.wait_for_timeout(1000)
            html = page.content()
            browser.close()

            soup = BeautifulSoup(html, "html.parser")

            # Verificar si hay contenido real en los XHR capturados
            for resp in api_responses:
                body = resp["body"]
                if len(body) > 2000 and any(k in body for k in ["informe", "content", "texto", "body", "html"]):
                    # Intentar extraer HTML del JSON
                    import json
                    try:
                        data = json.loads(body)
                        content_str = str(data)
                        if len(content_str) > 3000:
                            return {
                                "success": True,
                                "html": f"<div class='api-content'><pre>{content_str[:50000]}</pre></div>",
                                "source": f"API intercept: {resp['url'][:80]}",
                            }
                    except Exception:
                        pass

            if _is_full_content(html):
                return {"success": True, "html": html, "source": "Navegador headless (Playwright)"}

    except Exception:
        pass

    return {"success": False}


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
