"""
Benchmark harness for VkusVill Smart Cart matching.
Tests all three stages: substring, Levenshtein, trigram cosine.
Usage: python benchmark.py
"""
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SKILL_DIR))
from match import match_all, match_substring, match_levenshtein, match_embedding, load_prefs


TEST_CASES = [
    # (query, expected_xml_id, description)
    ("нарзан", 56160, "точное совпадение ключа"),
    ("сок", 21101, "слово внутри ключа"),
    ("нарзaн", 56160, "латиница (опечатка)"),
    ("запеканка", 69, "точное совпадение"),
    ("творожная запеканка", 69, "перестановка слов"),
    ("кефир", None, "нет в prefs - должно быть MISS"),
    ("запеканк", 69, "неполное слово"),
    ("морковный", 21101, "часть ключа"),
    ("сок детский морковный", 21101, "полное название"),
    ("вода минеральная", None, "семантическое — trigrams не ловят"),
]

# Cases that specifically test trigram cosine
TRIGRAM_CASES = [
    ("творожная запеканка", 69, "порядок слов в ключе"),
    ("запеканка творожная", 69, "обратный порядок"),
    ("морковный сок детский", 21101, "перестановка 3 слов"),
    ("сок детский морковный", 21101, "ещё перестановка"),
    ("вода минеральная", None, "семантика — не ловится"),
    ("минералка", None, "разговорное — не ловится"),
]


def run():
    prefs = load_prefs()
    n_products = len(prefs.get("products", {}))
    print(f"Products in prefs: {n_products}")
    print()

    # Main benchmark
    results = {
        "substring": {"hits": 0, "miss": 0},
        "levenshtein": {"hits": 0, "miss": 0},
        "embedding": {"hits": 0, "miss": 0},
        "winner": {"hits": 0, "miss": 0},
    }
    total = len(TEST_CASES)

    for query, expected, desc in TEST_CASES:
        r = match_all(query, benchmark=True)
        w = r.get("winner")
        wstage = r.get("winner_stage") or "none"

        sub_ok = _check(r.get("substring"), expected)
        lev_ok = _check(r.get("levenshtein"), expected)
        emb_ok = _check(r.get("embedding"), expected)
        win_ok = _check(w, expected)

        for stage, ok in [("substring", sub_ok), ("levenshtein", lev_ok),
                           ("embedding", emb_ok), ("winner", win_ok)]:
            if ok:
                results[stage]["hits"] += 1
            else:
                results[stage]["miss"] += 1

        wid = w['xml_id'] if w else "MISS"
        print(f"[{wstage:15s}] '{query}' -> {wid}  ({desc})")

    print()
    print(f"{'Stage':<15s} {'Hits':>5s} {'Miss':>5s} {'Rate':>6s}")
    print(f"{'─'*15} {'─'*5} {'─'*5} {'─'*6}")
    for stage in ["substring", "levenshtein", "embedding", "winner"]:
        s = results[stage]
        rate = s["hits"] / total * 100
        print(f"{stage:<15s} {s['hits']:>5d} {s['miss']:>5d} {rate:>5.0f}%")

    # Trigram cosine analysis
    print()
    print("Trigram cosine specific cases:")
    for query, expected, desc in TRIGRAM_CASES:
        emb = match_embedding(query, prefs)
        if emb:
            ok = "✓" if emb["xml_id"] == expected else "✗"
            print(f"  {ok} '{query}' -> {emb['name']}  sim={emb['similarity']} via {emb['source']}")
        else:
            ok = "✓" if expected is None else "✗"
            print(f"  {ok} '{query}' -> MISS")


def _check(match, expected):
    if match is None:
        return expected is None
    if expected is None:
        return False
    return match.get("xml_id") == expected


if __name__ == "__main__":
    run()