"""
Three-way matcher for VkusVill Smart Cart.
Stages: substring → Levenshtein → embedding cosine.
Run as: python match.py "user query"   or   from match import match_all
"""
import json
import sys
from pathlib import Path

PREFS_PATH = Path.home() / ".hermes" / "vkusvill_prefs.json"


# ── Utilities ────────────────────────────────────────────────────────────

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
                prev[j + 1] + 1,      # deletion
                curr[j] + 1,           # insertion
                prev[j] + (ca != cb)   # substitution
            ))
        prev = curr
    return prev[-1]


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Cosine similarity between two equal-length float vectors."""
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = (sum(a * a for a in vec_a)) ** 0.5
    norm_b = (sum(b * b for b in vec_b)) ** 0.5
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


# ── Prefs loading ────────────────────────────────────────────────────────

def load_prefs() -> dict:
    """Load prefs file. Returns empty v2 structure if missing or legacy."""
    if not PREFS_PATH.exists():
        return {"version": 2, "products": {}}
    raw = json.loads(PREFS_PATH.read_text())
    # Auto-migrate v1 to v2
    if "products" not in raw:
        products = {}
        key_index = {}
        for key, val in raw.items():
            if isinstance(val, dict) and "xml_id" in val:
                sid = str(val["xml_id"])
                if sid not in products:
                    products[sid] = {"name": val["name"], "keys": [], "vector": None}
                products[sid]["keys"].append(key)
        raw = {"version": 2, "products": products}
    return raw


def _all_keys(prefs: dict) -> dict:
    """Flatten: key→{xml_id, name} for substring/levenshtein matching."""
    result = {}
    for xml_id, prod in prefs.get("products", {}).items():
        for key in prod.get("keys", []):
            result[key] = {"xml_id": int(xml_id), "name": prod["name"]}
    return result


# ── Stage 1: Substring ──────────────────────────────────────────────────

def match_substring(query: str, prefs: dict) -> dict | None:
    """
    Two-pass substring matching.
    Pass 1: key is substring of query.
    Pass 2: word from query is substring of key (scored by shared word count).
    """
    text = query.lower().strip()
    all_keys = _all_keys(prefs)

    # Pass 1 — key in query
    for key, info in all_keys.items():
        if key.lower() in text:
            return {"stage": "substring_p1", "key": key, **info}

    # Pass 2 — word in key (score by shared words, break ties by key length)
    words = [w for w in text.split() if len(w) > 2]
    if not words:
        return None

    best_key = None
    best_info = None
    best_score = -1

    for word in words:
        for key, info in all_keys.items():
            if word in key.lower():
                score = sum(1 for w in words if w in key.lower())
                if score > best_score or (
                    score == best_score
                    and best_key is not None
                    and len(key) > len(best_key)
                ):
                    best_key = key
                    best_info = info
                    best_score = score

    if best_key:
        return {"stage": "substring_p2", "key": best_key, "score": best_score, **best_info}
    return None


# ── Stage 2: Levenshtein ────────────────────────────────────────────────

def match_levenshtein(query: str, prefs: dict) -> dict | None:
    """
    Normalized Levenshtein: compare each WORD of query against each WORD of key.
    Threshold: ≤ 0.25.
    """
    query_lower = query.lower().strip()
    all_keys = _all_keys(prefs)
    best_key = None
    best_info = None
    best_dist = float("inf")
    best_matched = ""

    for key, info in all_keys.items():
        key_lower = key.lower()
        for kw in key_lower.split():
            if len(kw) < 3:
                continue
            # Compare this key word against each query word
            for qw in query_lower.split():
                if len(qw) < 3:
                    continue
                dist = levenshtein(qw, kw)
                norm = dist / max(len(qw), len(kw))
                if norm < best_dist:
                    best_dist = norm
                    best_key = key
                    best_info = info
                    best_matched = f"qw='{qw}' kw='{kw}'"

    if best_key and best_dist <= 0.25:
        return {
            "stage": "levenshtein",
            "key": best_key,
            "xml_id": best_info["xml_id"],
            "name": best_info["name"],
            "distance": round(best_dist, 3),
            "matched": best_matched,
        }
    return None


# ── Stage 3: Character trigram cosine ────────────────────────────────────

def char_trigrams(s: str) -> dict[str, float]:
    """
    Extract character trigrams with start/end padding.
    Returns {trigram: count} as float for cosine compatibility.
    Example: "молоко" → {"  м":1, " мо":1, "мол":1, "оло":1, "лок":1, "око":1, "ко ":1}
    """
    s = "  " + s.lower() + " "
    grams: dict[str, float] = {}
    for i in range(len(s) - 2):
        g = s[i:i+3]
        grams[g] = grams.get(g, 0) + 1.0
    return grams


def trigram_cosine(grams_a: dict[str, float], grams_b: dict[str, float]) -> float:
    """Cosine similarity between two trigram count dicts."""
    all_keys = set(grams_a) | set(grams_b)
    dot = sum(grams_a.get(k, 0.0) * grams_b.get(k, 0.0) for k in all_keys)
    norm_a = (sum(v ** 2 for v in grams_a.values())) ** 0.5
    norm_b = (sum(v ** 2 for v in grams_b.values())) ** 0.5
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def match_embedding(query: str, prefs: dict) -> dict | None:
    """
    Stage 3: character trigram cosine similarity.
    Compares query trigrams against product names AND keys.
    No external dependencies — pure Python math.
    Threshold: ≥ 0.75.
    """
    text = query.lower().strip()
    query_grams = char_trigrams(text)

    best_xml = None
    best_prod = None
    best_sim = -1.0
    best_source = ""

    for xml_id, prod in prefs.get("products", {}).items():
        # Compare against product name
        sim = trigram_cosine(query_grams, char_trigrams(prod["name"]))
        if sim > best_sim:
            best_sim = sim
            best_xml = xml_id
            best_prod = prod
            best_source = "name"

        # Also compare against each key (may be a better match)
        for key in prod.get("keys", []):
            sim = trigram_cosine(query_grams, char_trigrams(key))
            if sim > best_sim:
                best_sim = sim
                best_xml = xml_id
                best_prod = prod
                best_source = f"key:{key}"

    if best_prod and best_sim >= 0.75:
        return {
            "stage": "embedding",
            "xml_id": int(best_xml),
            "name": best_prod["name"],
            "similarity": round(best_sim, 3),
            "source": best_source,
        }
    return None


# ── Orchestrator ────────────────────────────────────────────────────────

def match_all(query: str, benchmark: bool = False) -> dict:
    """
    Run all three stages. Return winner + optional benchmark data.

    Args:
        query: user's raw input (e.g. "добавь нарзан")
        benchmark: if True, include scores from all stages

    Returns:
        {
            "winner": {...} | null,
            "winner_stage": "substring_p1" | "levenshtein" | "embedding",
            # only when benchmark=True:
            "substring": {...} | null,
            "levenshtein": {...} | null,
            "embedding": {...} | null,
        }
    """
    prefs = load_prefs()
    result = {"query": query, "winner": None, "winner_stage": None}

    # Stage 1
    sub = match_substring(query, prefs)
    if benchmark:
        result["substring"] = sub
    if sub:
        result["winner"] = sub
        result["winner_stage"] = sub["stage"]
        return result

    # Stage 2
    lev = match_levenshtein(query, prefs)
    if benchmark:
        result["levenshtein"] = lev
    if lev:
        result["winner"] = lev
        result["winner_stage"] = "levenshtein"
        return result

    # Stage 3
    emb = match_embedding(query, prefs)
    if benchmark:
        result["embedding"] = emb
    if emb:
        result["winner"] = emb
        result["winner_stage"] = "embedding"
        return result

    # No match at all — return full result when benchmarking
    if benchmark:
        return result

    return result


# ── CLI entry point (for manual testing) ────────────────────────────────

if __name__ == "__main__":
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "молоко"
    result = match_all(query, benchmark=True)
    print(json.dumps(result, ensure_ascii=False, indent=2))