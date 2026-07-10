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
    const items = q.split(/[\\s,\\n]+/).filter(s => s).slice(0, 20);
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

    # ── Stage 0: split every query into individual words ──
    # Client already splits by commas/newlines, but may send
    # multi-word items like "нарзан мандарины" (no comma).
    # Always normalize to individual tokens.
    tokens: list[str] = []
    seen_tokens = set()
    for q in queries:
        for w in q.split():
            w = w.strip().lower()
            if w and w not in seen_tokens:
                seen_tokens.add(w)
                tokens.append(w)

    # ── Stage 1: quick-order (instant) ──
    qo_result = resolve_all(tokens)
    # resolved_by_idx[i] = match dict or None
    resolved_by_idx: list[dict | str | None] = [None] * len(tokens)
    for r in qo_result["resolved"]:
        # Find the token index by query text
        try:
            idx = tokens.index(r["query"])
            if r.get("product_id") and not r.get("xml_id"):
                r["xml_id"] = r["product_id"]
            resolved_by_idx[idx] = r
        except ValueError:
            pass

    # ── Stage 2: match_all for unresolved tokens ──
    for i, t in enumerate(tokens):
        if resolved_by_idx[i] is not None:
            continue
        m = match_all(t)
        if m.get("winner"):
            w = m["winner"]
            resolved_by_idx[i] = {
                "query": t,
                "xml_id": w.get("xml_id"),
                "name": w.get("name", t),
                "stage": w.get("stage", "?"),
                "q": 1,
            }

    # ── Stage 2b: join unmatched words with neighbours ──
    # If a word didn't match alone (often an adjective: "бездрожжевой",
    # "топлёное", "творожные"), try joining with adjacent word(s).
    # BUT: only join if the result is actually different — not just
    # a substring match that swallows the unmatched word.
    def _xml_id_of(r: dict | str | None) -> int | None:
        if isinstance(r, dict):
            return r.get("xml_id") or r.get("product_id")
        return None

    i = 0
    while i < len(tokens):
        if resolved_by_idx[i] is not None:
            i += 1
            continue
        # tokens[i] is unmatched — try joining
        # Try: prev + current
        if i > 0 and resolved_by_idx[i-1] is not None:
            prev_xml = _xml_id_of(resolved_by_idx[i-1])
            phrase = tokens[i-1] + " " + tokens[i]
            m = match_all(phrase)
            w = m.get("winner")
            if w and _xml_id_of(w) != prev_xml:
                # Join found a DIFFERENT product — replace prev
                resolved_by_idx[i-1] = {
                    "query": phrase,
                    "xml_id": w.get("xml_id"),
                    "name": w.get("name", phrase),
                    "stage": w.get("stage", "?"),
                    "q": 1,
                }
                resolved_by_idx[i] = "__merged__"
                i += 1
                continue
            # else: join matched the same product — don't swallow the word
        # Try: current + next (both unmatched)
        if i + 1 < len(tokens) and resolved_by_idx[i+1] is None:
            phrase = tokens[i] + " " + tokens[i+1]
            m = match_all(phrase)
            w = m.get("winner")
            if w:
                resolved_by_idx[i] = {
                    "query": phrase,
                    "xml_id": w.get("xml_id"),
                    "name": w.get("name", phrase),
                    "stage": w.get("stage", "?"),
                    "q": 1,
                }
                resolved_by_idx[i+1] = "__merged__"
                i += 2
                continue
        i += 1

    # ── Collect results ──
    resolved = [r for r in resolved_by_idx if r is not None and r != "__merged__"]
    still_unresolved = [tokens[i] for i, r in enumerate(resolved_by_idx) if r is None]

    # Build cart products list
    cart_products: list[dict] = []
    for r in resolved:
        if not isinstance(r, dict):
            continue
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
