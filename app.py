"""
VkusVill Cart Server — Flask app.

Endpoints:
  GET  /              — HTML frontend
  POST /api/match     — {"q": "нарзан"} → {"matches": [...], "unresolved": [...]}
  POST /api/cart      — {"products": [{"xml_id": 1, "q": 1}, ...]} → {"url": "..."}
  POST /api/resolve   — {"items": ["нарзан", "сырники"]} → full pipeline to cart
  GET  /health        — {"ok": true}
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from flask import Flask, request, jsonify, send_from_directory, render_template_string

# ── Path setup: skills are vendored inside the project ────────────────────
HERE = Path(__file__).resolve().parent
SKILLS_DIR = HERE / "skills"
PREFS_PATH = HERE / "vkusvill_prefs.json"

# Make scripts importable
sys.path.insert(0, str(SKILLS_DIR / "vkusvill-quick-order" / "scripts"))
sys.path.insert(0, str(SKILLS_DIR / "vkusvill-smart-cart" / "scripts"))

from resolver import resolve, resolve_all
from match import match_all
import match as _match
_match.PREFS_PATH = HERE / "vkusvill_prefs.json"
from mcp_client import search_products_parsed, create_cart_link

app = Flask(__name__, static_folder="static", static_url_path="")


# ── HTML index ─────────────────────────────────────────────────────────────

INDEX_HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ВкусВилл — заказ</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: #1a1a2e; color: #e0e0e0; min-height: 100vh;
         display: flex; justify-content: center; padding: 20px; }
  .app { max-width: 600px; width: 100%; }
  h1 { color: #00d2a0; font-size: 28px; margin-bottom: 8px; text-align: center; }
  .sub { text-align: center; color: #888; margin-bottom: 24px; font-size: 14px; }
  textarea { width: 100%; height: 100px; padding: 14px; font-size: 16px;
             border: 2px solid #333; border-radius: 12px; background: #16213e;
             color: #e0e0e0; resize: vertical; font-family: inherit; }
  textarea:focus { outline: none; border-color: #00d2a0; }
  button { width: 100%; padding: 14px; font-size: 18px; margin-top: 12px;
           background: #00d2a0; color: #1a1a2e; border: none; border-radius: 12px;
           font-weight: 700; cursor: pointer; transition: background .2s; }
  button:hover { background: #00e6b0; }
  button:disabled { background: #444; color: #888; cursor: not-allowed; }
  .result { margin-top: 20px; }
  .cart-link { display: block; padding: 16px; background: #16213e; border-radius: 12px;
               border: 1px solid #00d2a0; text-align: center; font-size: 16px;
               color: #00d2a0; text-decoration: none; margin-bottom: 16px; }
  .cart-link:hover { background: #1c2d54; }
  .item { padding: 10px 14px; background: #16213e; border-radius: 8px;
          margin-bottom: 6px; display: flex; justify-content: space-between;
          align-items: center; }
  .item .name { font-size: 14px; }
  .item .stage { font-size: 11px; color: #888; }
  .notfound { padding: 10px 14px; color: #ff6b6b; font-size: 14px; }
  .error { padding: 16px; background: #3d1515; border-radius: 12px; color: #ff6b6b; }
  .spinner { display: none; text-align: center; padding: 20px; color: #888; }
  .spinner.active { display: block; }
</style>
</head>
<body>
<div class="app">
  <h1>🛒 ВкусВилл</h1>
  <div class="sub">Введи список покупок — получи ссылку на корзину</div>
  <textarea id="query" placeholder="нарзан&#10;сырники&#10;бефстроганов&#10;хлеб бездрожжевой"
            autofocus></textarea>
  <button id="go" onclick="doResolve()">Собрать корзину →</button>
  <div class="spinner" id="spin">🔄 Ищем и собираем...</div>
  <div class="result" id="result"></div>
</div>
<script>
async function doResolve() {
  const q = document.getElementById('query').value.trim();
  if (!q) return;
  const go = document.getElementById('go');
  const spin = document.getElementById('spin');
  const result = document.getElementById('result');
  go.disabled = true;
  spin.classList.add('active');
  try {
    const items = q.split(/[\n,]+/).map(s => s.trim()).filter(s => s);
    if (items.length === 1 && items[0].includes(' ')) {
      items.splice(0, 1, ...items[0].split(/\s+/).filter(s => s));
    }
    items.splice(20);
    const resp = await fetch('/api/resolve', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({items})
    });
    const data = await resp.json();
    let html = '';
    if (data.url) {
      html += `<a class="cart-link" href="${data.url}" target="_blank">🛍 Открыть корзину (${data.matched} товаров) →</a>`;
    }
    for (const m of data.matches || []) {
      html += `<div class="item"><span class="name">${esc(m.name || m.query)}</span></div>`;
    }
    for (const u of data.unmatched || []) {
      html += `<div class="notfound">⚠ Не найдено: ${esc(u)}</div>`;
    }
    if (!data.url && (data.matches||[]).length === 0) {
      html += '<div class="notfound">Ничего не найдено. Попробуй другие названия.</div>';
    }
    result.innerHTML = html;
  } catch (e) {
    result.innerHTML = `<div class="error">Ошибка: ${esc(String(e))}</div>`;
  } finally {
    go.disabled = false;
    spin.classList.remove('active');
  }
}
function esc(s) { const d=document.createElement('div'); d.textContent=s; return d.innerHTML; }
</script>
</body>
</html>"""


# ── Routes ─────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template_string(INDEX_HTML)


@app.route("/health")
def health():
    return jsonify(ok=True)


@app.route("/api/match", methods=["POST"])
def api_match():
    """Match a single query against local prefs."""
    data = request.get_json(force=True)
    q = (data.get("q") or "").strip()
    if not q:
        return jsonify(matches=[], error="empty query")
    result = match_all(q)
    return jsonify(result)


@app.route("/api/cart", methods=["POST"])
def api_cart():
    """Create a cart link from xml_id list."""
    data = request.get_json(force=True)
    products = data.get("products", [])
    if not products:
        return jsonify(error="no products"), 400
    try:
        url = create_cart_link(products)
        return jsonify(url=url, count=len(products))
    except Exception as e:
        return jsonify(error=str(e)), 502


@app.route("/api/resolve", methods=["POST"])
def api_resolve():
    """Full pipeline: items[] → match → cart link.

    Accepts: {"items": ["нарзан", "сырники", "бефстроганов"]}
    Returns: {"url": "...", "matches": [...], "matched": N, "unmatched": [...]}
    """
    data = request.get_json(force=True)
    items = data.get("items", [])
    if not items:
        return jsonify(error="empty items"), 400

    # Deduplicate
    seen = set()
    queries: list[str] = []
    for it in items:
        key = it.strip().lower()
        if key and key not in seen:
            seen.add(key)
            queries.append(key)
    if not queries:
        return jsonify(error="empty items after dedup"), 400

    # Split space-separated queries into individual words
    # Only split when 3+ words (likely a list); 1-2 words stay intact
    # so "хлеб бездрожжевой" remains one query.
    expanded: list[str] = []
    for q in queries:
        words = q.split()
        if len(words) >= 3:
            for w in words:
                w = w.strip().lower()
                if w and w not in seen:
                    seen.add(w)
                    expanded.append(w)
        else:
            expanded.append(q)
    queries = expanded

    # Stage 1: quick-order resolver (instant, zero-token)
    qo_result = resolve_all(queries)
    resolved: list[dict] = qo_result["resolved"]
    unresolved: list[str] = qo_result["unresolved"]

    # Normalise: resolver returns product_id, match_all returns xml_id.
    # Unify to xml_id for downstream consistency.
    for r in resolved:
        if r.get("product_id") and not r.get("xml_id"):
            r["xml_id"] = r["product_id"]

    # Stage 2: smart-cart match_all for unresolved
    still_unresolved: list[str] = []
    for q in unresolved:
        m = match_all(q)
        if m.get("winner"):
            w = m["winner"]
            resolved.append({
                "query": q,
                "xml_id": w.get("xml_id"),
                "name": w.get("name", q),
                "stage": w.get("stage", "?"),
                "q": 1,
            })
        else:
            still_unresolved.append(q)

    # Stage 2b: for space-separated queries that didn't match,
    # try each word individually
    retry_unresolved: list[str] = []
    for q in still_unresolved:
        if ' ' not in q:
            retry_unresolved.append(q)
            continue
        words = q.split()
        found_any = False
        for w in words:
            m = match_all(w)
            if m.get("winner"):
                found_any = True
                winner = m["winner"]
                resolved.append({
                    "query": w,
                    "xml_id": winner.get("xml_id"),
                    "name": winner.get("name", w),
                    "stage": winner.get("stage", "?"),
                    "q": 1,
                })
        if not found_any:
            retry_unresolved.append(q)
    still_unresolved = retry_unresolved

    # Build cart products list
    cart_products: list[dict] = []
    for r in resolved:
        xml_id = r.get("xml_id")
        if xml_id:
            cart_products.append({
                "xml_id": int(xml_id),
                "q": int(r.get("q", 1)),
            })

    # Create cart link (if any products found)
    url: str | None = None
    cart_ok = False
    if cart_products:
        try:
            url = create_cart_link(cart_products)
            cart_ok = True
        except Exception as e:
            # Cart creation failed — return matches anyway (offline mode)
            return jsonify(
                url=None,
                matches=resolved,
                matched=len(resolved),
                unmatched=still_unresolved,
                cart_error=f"MCP недоступен: {e}",
                offline=True,
            )

    return jsonify(
        url=url,
        matches=resolved,
        matched=len(resolved),
        unmatched=still_unresolved,
    )


# ── Main ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="VkusVill Cart Server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    print(f"🍏 VkusVill Cart Server → http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=args.debug)
