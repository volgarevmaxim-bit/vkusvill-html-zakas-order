"""
Prefs manager for VkusVill Smart Cart v2.
Handles adding products, merging keys, and migrating v1→v2.
No external dependencies — pure Python + JSON.
"""
import json
from pathlib import Path

PREFS_PATH = Path.home() / ".hermes" / "vkusvill_prefs.json"


def load_prefs() -> dict:
    """Load prefs. Auto-migrate v1 on read."""
    if not PREFS_PATH.exists():
        return {"version": 2, "products": {}}
    raw = json.loads(PREFS_PATH.read_text())
    if "products" not in raw:
        raw = _migrate_v1_to_v2_inplace(raw)
        PREFS_PATH.write_text(json.dumps(raw, ensure_ascii=False, indent=2))
    return raw


def _migrate_v1_to_v2_inplace(raw: dict) -> dict:
    """Convert flat {key: {xml_id, name}} → {version:2, products: {id: {name, keys}}}."""
    products = {}
    for key, val in raw.items():
        if not isinstance(val, dict) or "xml_id" not in val:
            continue
        sid = str(val["xml_id"])
        if sid not in products:
            products[sid] = {"name": val["name"], "keys": []}
        if key not in products[sid]["keys"]:
            products[sid]["keys"].append(key)
    return {"version": 2, "products": products}


def add_product(xml_id: int, name: str, keys: list[str]) -> dict:
    """
    Add a new product or merge keys into existing one.
    Returns {"ok": True, "keys_added": N} or {"ok": False, "error": ...}
    """
    prefs = load_prefs()
    sid = str(xml_id)

    if sid in prefs.get("products", {}):
        existing = set(prefs["products"][sid].get("keys", []))
        new_keys = [k for k in keys if k not in existing]
        prefs["products"][sid]["keys"].extend(new_keys)
        PREFS_PATH.write_text(json.dumps(prefs, ensure_ascii=False, indent=2))
        return {"ok": True, "keys_added": len(new_keys), "existing": True}

    prefs["products"][sid] = {"name": name, "keys": list(keys)}
    PREFS_PATH.write_text(json.dumps(prefs, ensure_ascii=False, indent=2))
    return {"ok": True, "keys_added": len(keys)}


def list_products() -> list[dict]:
    """Return all products as a flat list."""
    prefs = load_prefs()
    result = []
    for xml_id, prod in prefs.get("products", {}).items():
        result.append({
            "xml_id": int(xml_id),
            "name": prod["name"],
            "keys": prod.get("keys", []),
        })
    return result


def remove_product(xml_id: int) -> dict:
    """Remove a product and all its keys."""
    prefs = load_prefs()
    sid = str(xml_id)
    if sid in prefs.get("products", {}):
        name = prefs["products"][sid]["name"]
        del prefs["products"][sid]
        PREFS_PATH.write_text(json.dumps(prefs, ensure_ascii=False, indent=2))
        return {"ok": True, "removed": name}
    return {"ok": False, "error": f"xml_id {xml_id} not found"}


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python embed.py add <xml_id> <name> <key1> [key2...]")
        print("  python embed.py list")
        print("  python embed.py remove <xml_id>")
        print("  python embed.py migrate")
        sys.exit(0)

    cmd = sys.argv[1]
    if cmd == "add" and len(sys.argv) >= 4:
        result = add_product(int(sys.argv[2]), sys.argv[3], sys.argv[4:])
    elif cmd == "list":
        result = list_products()
    elif cmd == "remove" and len(sys.argv) >= 3:
        result = remove_product(int(sys.argv[2]))
    elif cmd == "migrate":
        prefs = load_prefs()
        result = {"ok": True, "products": len(prefs.get("products", {}))}
    else:
        result = {"ok": False, "error": "invalid arguments"}

    print(json.dumps(result, ensure_ascii=False, indent=2))