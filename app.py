#!/usr/bin/env python3
"""
Paywall Bypass Tool - Intenta acceder a contenido de pago usando métodos alternativos.
"""

import urllib.parse
from flask import Flask, render_template, request, jsonify
import requests
from bs4 import BeautifulSoup

app = Flask(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

READER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 "
                  "(KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://www.google.es/",
}


def clean_html(html: str, base_url: str) -> str:
    """Extrae el contenido principal eliminando overlays y paywalls."""
    soup = BeautifulSoup(html, "html.parser")

    # Eliminar elementos comunes de paywall/overlay
    paywall_selectors = [
        ".paywall", ".paywalled", ".paywall-overlay", ".paywall-modal",
        ".subscription-wall", ".subscribe-wall", ".premium-overlay",
        ".modal-overlay", ".cookie-overlay", ".modal-backdrop",
        "[class*='paywall']", "[class*='suscri']", "[class*='subscri']",
        "[id*='paywall']", "[id*='overlay']",
        "aside", ".aside", ".sidebar",
        ".newsletter-popup", ".newsletter-overlay",
    ]
    for selector in paywall_selectors:
        for el in soup.select(selector):
            el.decompose()

    # Intentar extraer el artículo principal
    content_selectors = [
        "article", ".article-body", ".article-content", ".article__body",
        ".entry-content", ".post-content", ".content-body",
        ".news-body", ".informe-content", ".report-content",
        "main", ".main-content", "#main-content", "#content",
        ".story-body", ".body-text",
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
    for tag in content.find_all(["img", "a"], href=True):
        for attr in ["href", "src"]:
            val = tag.get(attr, "")
            if val.startswith("/"):
                tag[attr] = base + val

    return str(content)


def _get(url: str, headers: dict, timeout: int = 15):
    """Wrapper de requests.get con manejo de errores de red/proxy."""
    try:
        r = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        if r.status_code == 200 and len(r.text) > 500:
            return r
    except (requests.exceptions.ProxyError,
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
            requests.exceptions.RequestException):
        pass
    return None


def try_direct(url: str) -> dict:
    """Acceso directo simulando Googlebot."""
    r = _get(url, HEADERS)
    if r:
        return {"success": True, "html": r.text, "source": "Acceso directo (Googlebot UA)"}
    return {"success": False}


def try_referer_google(url: str) -> dict:
    """Acceso simulando llegar desde Google."""
    headers = READER_HEADERS.copy()
    headers["Referer"] = "https://www.google.es/search?q=" + urllib.parse.quote(url)
    r = _get(url, headers)
    if r:
        return {"success": True, "html": r.text, "source": "Referer Google"}
    return {"success": False}


def try_wayback_machine(url: str) -> dict:
    """Busca en Wayback Machine (archive.org)."""
    api = f"http://archive.org/wayback/available?url={urllib.parse.quote(url)}"
    r = _get(api, READER_HEADERS, timeout=10)
    if not r:
        return {"success": False}
    try:
        data = r.json()
        snapshot = data.get("archived_snapshots", {}).get("closest", {})
        if snapshot.get("available") and snapshot.get("url"):
            archive_url = snapshot["url"]
            r2 = _get(archive_url, READER_HEADERS, timeout=20)
            if r2:
                return {
                    "success": True,
                    "html": r2.text,
                    "source": f"Wayback Machine ({snapshot.get('timestamp', '')})",
                    "archive_url": archive_url,
                }
    except Exception:
        pass
    return {"success": False}


def try_12ft(url: str) -> dict:
    """Usa el servicio 12ft.io para saltar paywalls."""
    proxy_url = f"https://12ft.io/proxy?q={urllib.parse.quote(url)}"
    r = _get(proxy_url, READER_HEADERS, timeout=20)
    if r:
        return {"success": True, "html": r.text, "source": "12ft.io", "proxy_url": proxy_url}
    return {"success": False}


def try_google_cache(url: str) -> dict:
    """Busca en caché de Google."""
    cache_url = f"https://webcache.googleusercontent.com/search?q=cache:{urllib.parse.quote(url)}&hl=es"
    r = _get(cache_url, HEADERS)
    if r:
        return {"success": True, "html": r.text, "source": "Google Cache", "cache_url": cache_url}
    return {"success": False}


METHODS = [
    ("direct", try_direct),
    ("google_referer", try_referer_google),
    ("12ft", try_12ft),
    ("google_cache", try_google_cache),
    ("wayback", try_wayback_machine),
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

    results = []
    for name, method in METHODS:
        result = method(url)
        result["method"] = name
        if result.get("success"):
            result["content"] = clean_html(result.pop("html"), url)
            results.append(result)
            break
        else:
            results.append(result)

    successes = [r for r in results if r.get("success")]
    if successes:
        return jsonify({"success": True, "result": successes[0], "tried": len(results)})

    alternatives = {
        "wayback_search": f"https://web.archive.org/web/*/{url}",
        "12ft_link": f"https://12ft.io/proxy?q={urllib.parse.quote(url)}",
        "google_cache": f"https://webcache.googleusercontent.com/search?q=cache:{urllib.parse.quote(url)}",
        "archive_today": f"https://archive.ph/{url}",
    }
    return jsonify({"success": False, "alternatives": alternatives, "tried": len(results)})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
