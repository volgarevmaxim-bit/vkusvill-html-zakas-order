"""
MCP JSON-RPC 2.0 client for VkusVill API.
Zero dependencies beyond stdlib + requests.
Endpoint: https://mcp001.vkusvill.ru/mcp
"""
from __future__ import annotations

import json
import urllib.request
import urllib.error
from typing import Any

MCP_URL = "https://mcp001.vkusvill.ru/mcp"
TIMEOUT = 20  # seconds
HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
    "User-Agent": "VkusVill-Cart-Server/1.0",
}
_request_id = 0


def _next_id() -> int:
    global _request_id
    _request_id += 1
    return _request_id


def _rpc(method: str, params: dict[str, Any]) -> dict[str, Any]:
    """Send a single JSON-RPC 2.0 request. Returns result dict or raises."""
    payload = {
        "jsonrpc": "2.0",
        "id": _next_id(),
        "method": method,
        "params": params,
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(MCP_URL, data=data, headers=HEADERS, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"MCP HTTP {e.code}: {body[:500]}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"MCP connection failed: {e.reason}") from e
    except Exception as e:
        raise RuntimeError(f"MCP request error: {e}") from e

    result = json.loads(raw)
    if "error" in result:
        err = result["error"]
        raise RuntimeError(f"MCP RPC error {err.get('code')}: {err.get('message')}")
    return result.get("result", {})


# ── Public API ────────────────────────────────────────────────────────────

def tools_call(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Call a VkusVill MCP tool by name.

    Returns the tool's result dict (content of ``tools/call.result``).
    """
    return _rpc("tools/call", {
        "name": tool_name,
        "arguments": arguments,
    })


def search_products(query: str, page: int = 1, vvonly: int = 1) -> dict[str, Any]:
    """Search VkusVill catalog. Returns raw MCP response dict.

    Result structure (truncated example):
      {"content": [{"type": "text", "text": "{\\"products\\": [{...}, ...], ...}"}]}
    """
    return tools_call("vkusvill_products_search", {
        "q": query,
        "page": page,
        "vvonly": vvonly,
    })


def search_products_parsed(query: str, page: int = 1) -> list[dict[str, Any]]:
    """Search and return parsed list of product dicts."""
    raw = search_products(query, page)
    return _parse_content(raw)


def create_cart_link(products: list[dict[str, Any]]) -> str:
    """Create a VkusVill cart link.

    Args:
        products: list of dicts like [{"xml_id": 56160, "q": 1}, ...]

    Returns:
        The cart URL string.
    """
    raw = tools_call("vkusvill_cart_link_create", {"products": products})
    parsed = _parse_content(raw)
    # Detect MCP internal errors wrapped inside content text
    if isinstance(parsed, dict) and parsed.get("ok") is False:
        err_info = parsed.get("error", {})
        raise RuntimeError(
            f"MCP cart error: {err_info.get('message', 'неизвестная ошибка')}"
        )
    # Try to extract the URL from whatever shape the API returns
    if isinstance(parsed, dict) and "url" in parsed:
        return parsed["url"]
    if isinstance(parsed, dict) and "link" in parsed:
        return parsed["link"]
    # MCP wraps response in {"ok": true, "data": {"link": "..."}}
    if isinstance(parsed, dict) and "data" in parsed:
        data_obj = parsed["data"]
        if isinstance(data_obj, dict):
            for key in ("url", "link", "cart_url", "cart_link"):
                if key in data_obj:
                    return str(data_obj[key])
    if isinstance(raw, dict):
        # Walk the nested structure looking for a URL
        for item in raw.get("content", []):
            text = item.get("text", "")
            try:
                inner = json.loads(text)
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(inner, dict):
                for key in ("url", "link", "cart_url", "cart_link"):
                    if key in inner:
                        return str(inner[key])
                if "data" in inner and isinstance(inner["data"], dict):
                    dd = inner["data"]
                    for key in ("url", "link", "cart_url", "cart_link"):
                        if key in dd:
                            return str(dd[key])
            if isinstance(inner, str) and inner.startswith("http"):
                return inner
    return str(raw)


def _parse_content(raw: dict[str, Any]) -> Any:
    """Extract parsed JSON from MCP content[0].text, or return raw as-is."""
    content = raw.get("content", [])
    if content and isinstance(content, list):
        item = content[0]
        if isinstance(item, dict) and "text" in item:
            try:
                return json.loads(item["text"])
            except (json.JSONDecodeError, TypeError):
                return item["text"]
    return raw


# ── Smoke-test on import ──────────────────────────────────────────────────
if __name__ == "__main__":
    print("=== products_search('нарзан') ===")
    r = search_products("нарзан")
    products = search_products_parsed("нарзан")
    if isinstance(products, list):
        print(f"  Found {len(products)} products")
        for p in products[:3]:
            print(f"  - [{p.get('xml_id')}] {p.get('name', p.get('title', '?'))} — {p.get('price', '?')}")
    else:
        print(f"  Raw result key count: {len(products) if isinstance(products, dict) else 'scalar'}")
