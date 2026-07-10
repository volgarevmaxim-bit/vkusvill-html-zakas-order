"""
Fast-path resolver for VkusVill Quick Order.
Stage flow: normalize → exact → aliases → simple fuzzy → None (fallback).

Zero external dependencies — pure Python stdlib.
Primary data source: products.csv in the same skill directory.
"""

import csv
import re
import json
from pathlib import Path
from datetime import datetime, timezone

SKILL_DIR = Path(__file__).resolve().parent.parent  # vkusvill-quick-order/
CSV_PATH = SKILL_DIR / "products.csv"
LOG_PATH = Path.home() / ".hermes" / "vkusvill_unresolved.log"

# ── Threshold ────────────────────────────────────────────────────────────
# Full-string normalized Levenshtein threshold.
# Stricter than smart-cart's per-word 0.25 because this is full-string.
FUZZY_THRESHOLD = 0.20


# ── Normalization ────────────────────────────────────────────────────────

def normalize(s: str) -> str:
    """Normalize: lowercase, collapse whitespace, strip quotes/dashes, dedup spaces."""
    s = s.lower().strip()
    s = re.sub(r"[«»""'']", "", s)       # strip quotes (all kinds)
    s = re.sub(r"\s*,\s*", " ", s)       # commas → spaces
    s = re.sub(r"\s*-\s*", " ", s)       # hyphens → spaces
    s = re.sub(r"[()]", " ", s)          # parens → spaces
    s = re.sub(r"\s{2,}", " ", s)        # collapse whitespace
    return s.strip()


# ── Levenshtein ──────────────────────────────────────────────────────────

def levenshtein(a: str, b: str) -> int:
    """Wagner-Fischer edit distance."""
    if len(a) < len(b):
        return levenshtein(b, a)
    if len(b) == 0:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr = [i + 1]
        for j, cb in enumerate(b):
            curr.append(min(
                prev[j + 1] + 1,
                curr[j] + 1,
                prev[j] + (ca != cb),
            ))
        prev = curr
    return prev[-1]


def norm_distance(a: str, b: str) -> float:
    """Normalized Levenshtein — 0.0 = identical, 1.0 = completely different."""
    return levenshtein(a, b) / max(len(a), len(b), 1)


# ── CSV loader ──────────────────────────────────────────────────────────

def _load_roster() -> list[dict]:
    """Load products.csv → list of {canonical_name, product_id, aliases: [str]}."""
    products = []
    with open(CSV_PATH, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            products.append({
                "canonical_name": row["canonical_name"],
                "product_id": int(row["product_id"]),
                "aliases": [a for a in row["aliases"].split("|") if a],
            })
    return products


# ── Stage matchers ──────────────────────────────────────────────────────

def _match_exact(norm_q: str, products: list[dict]) -> dict | None:
    """Exact match against canonical_name (normalized)."""
    for p in products:
        if normalize(p["canonical_name"]) == norm_q:
            return {
                "stage": "exact",
                "product_id": p["product_id"],
                "canonical_name": p["canonical_name"],
            }
    return None


def _match_aliases(norm_q: str, products: list[dict]) -> dict | None:
    """Match against any alias (normalized)."""
    for p in products:
        for alias in p["aliases"]:
            if normalize(alias) == norm_q:
                return {
                    "stage": "alias",
                    "product_id": p["product_id"],
                    "canonical_name": p["canonical_name"],
                    "matched_alias": alias,
                }
    return None


def _match_fuzzy(norm_q: str, products: list[dict]) -> dict | None:
    """Simple fuzzy: compare norm_q against canonical_name + all aliases.
    Uses full-string normalised Levenshtein. Best match under threshold wins."""
    if len(norm_q) < 3:
        return None  # too short for meaningful fuzzy

    best = None
    best_dist = float("inf")

    for p in products:
        # Check canonical name
        targets = [p["canonical_name"]] + list(p["aliases"])
        for target in targets:
            norm_t = normalize(target)
            dist = norm_distance(norm_q, norm_t)
            if dist < best_dist:
                best_dist = dist
                best = {
                    "stage": "fuzzy",
                    "product_id": p["product_id"],
                    "canonical_name": p["canonical_name"],
                    "matched_target": target,
                    "distance": round(dist, 3),
                }

    if best and best["distance"] <= FUZZY_THRESHOLD:
        return best
    return None


# ── Logging ──────────────────────────────────────────────────────────────

def _log_unresolved(query: str) -> None:
    """Append unresolved query to log file."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    entry = f"{ts} | {json.dumps(query, ensure_ascii=False)}\n"
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(entry)


# ── Main resolver ────────────────────────────────────────────────────────

def resolve(query: str) -> dict | None:
    """
    Resolve a user query to a product via fast path.

    Returns:
        {"product_id": 56160, "canonical_name": "Нарзан...", "stage": "alias"}
        or None if unmatched (→ fall back to vkusvill-smart-cart).

    Logs unresolved queries to ~/.hermes/vkusvill_unresolved.log.
    """
    if not query or not query.strip():
        return None

    norm_q = normalize(query)
    products = _load_roster()

    # Stage 1: Exact (canonical)
    match = _match_exact(norm_q, products)
    if match:
        return match

    # Stage 2: Alias
    match = _match_aliases(norm_q, products)
    if match:
        return match

    # Stage 3: Simple fuzzy
    match = _match_fuzzy(norm_q, products)
    if match:
        return match

    # Stage 4: No match — log and signal fallback
    _log_unresolved(query)
    return None


def resolve_all(queries: list[str]) -> dict:
    """
    Batch resolve. Returns {resolved: [...], unresolved: [...]}.
    """
    result = {"resolved": [], "unresolved": []}
    for q in queries:
        r = resolve(q)
        if r:
            result["resolved"].append({"query": q, **r})
        else:
            result["unresolved"].append(q)
    return result


def roster_stats() -> dict:
    """Return stats about the roster."""
    products = _load_roster()
    total_aliases = sum(len(p["aliases"]) for p in products)
    return {
        "total_products": len(products),
        "total_aliases": total_aliases,
        "csv_path": str(CSV_PATH),
    }


# ── CLI ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python resolver.py <query>")
        print("       python resolver.py stats")
        print("       python resolver.py batch <q1> <q2> ...")
        sys.exit(0)

    cmd = sys.argv[1]
    if cmd == "stats":
        print(json.dumps(roster_stats(), ensure_ascii=False, indent=2))
    elif cmd == "batch":
        queries = sys.argv[2:]
        result = resolve_all(queries)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        query = " ".join(sys.argv[1:])
        result = resolve(query)
        if result:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"UNRESOLVED: {query}")
            sys.exit(1)
