---
name: vkusvill-smart-cart
description: "Three-stage smart cart: substring → Levenshtein → trigram cosine."
version: 2.0.0
---

# VkusVill Smart Cart v2

Three-stage matching pipeline. Always use execute_code with `scripts/match.py` — never read prefs or do matching in LLM context. Zero external dependencies.

## Workflow

### 1. Match user request

```python
import sys
sys.path.insert(0, "~/.hermes/skills/vkusvill-smart-cart/scripts")
from match import match_all

result = match_all("<user query>")
```

Returns compact dict — LLM only sees `winner`:

```json
{"winner": {"stage": "levenshtein", "xml_id": 56160, "name": "Нарзан", "distance": 0.167},
 "winner_stage": "levenshtein"}
```

Stages (in order of priority):

| Stage | Method | Threshold | Catches |
|---|---|---|---|
| 1 | **substring** (two-pass: key→query, word→key) | — | Exact, partial, word-in-key |
| 2 | **Levenshtein** (per-word, normalized) | ≤ 0.25 | Typos, translit, misspellings |
| 3 | **Character trigram cosine** | ≥ 0.75 | Word-order variations |

### 2. If match found

Tell user what was matched and which stage. Use q=1 default. Add to cart via `vkusvill_cart_link_create`.

### 3. If no match — search

Use `vkusvill_products_search`. Let user pick. Then offer to save to prefs via `scripts/embed.py`.

### 4. Save new product

Use execute_code calling `scripts/embed.py`:

```python
sys.path.insert(0, "~/.hermes/skills/vkusvill-smart-cart/scripts")
from embed import add_product
add_product(xml_id=12345, name="Молоко 3,2%, 1 л", keys=["молоко", "молоко 3.2"])
```

Always add at least 2 key variants with different word order. Vectors are computed on-the-fly (trigrams), no pre-computation needed.

### 5. Bulk add (many products at once)

When user gives a list of product names without xml_ids:

1. Deduplicate the list.
2. Search in parallel batches of ~15 using `vkusvill_products_search`. Use the first result whose name matches. Skip products already in prefs.
3. Batch-add via execute_code:

```python
sys.path.insert(0, "~/.hermes/skills/vkusvill-smart-cart/scripts")
from embed import add_product
for xml_id, name, keys in products:
    add_product(xml_id, name, keys)
```

4. Report added count + list of unfound products (need manual xml_id lookup).

### 6. Benchmark

Add `benchmark=true` to match_all for scores from all three stages:

```python
result = match_all("нарзaн", benchmark=True)
# result["substring"]   → None
# result["levenshtein"]  → {stage, xml_id, distance, matched_word}
# result["embedding"]    → {stage, xml_id, similarity, source}
# result["winner"]       → best match
```

Or run `python scripts/benchmark.py` for a full test suite.

## Prefs format (v2)

`~/.hermes/vkusvill_prefs.json`:

```json
{
  "version": 2,
  "products": {
    "56160": {
      "name": "Вода минеральная 'Нарзан' природной газации, 1 л",
      "keys": ["нарзан", "вода нарзан", "нарзан 1л"]
    }
  }
}
```

Multiple keys per product. Trigram vectors are computed at match time — no vector storage needed.

## Pitfalls

- **External brands often missing**: Продукты сторонних брендов (Агуша, Мираторг, Parmalat, Экологика, Бондюэль, Село Зеленое) часто отсутствуют в каталоге ВкусВилл. Если поиск не дал точного совпадения на первой странице — не переискивать, сообщить пользователю что товар не найден.
- **Deduplicate before searching**: пользователь может повторить товар в списке (напр. «Филе форели на пару» встречается дважды) — проверять существование в prefs перед поиском.
- **Multi-product queries**: Когда пользователь перечисляет несколько товаров в одном запросе (напр. «Нарзан Шишкин лес 400 мл»), `match_all()` обрабатывает запрос как единую поисковую строку и может найти совпадение только для одного товара, молча проигнорировав остальные. Если winner покрывает лишь часть слов из запроса — это сигнал что в запросе могло быть несколько товаров. В таком случае: уточнить у пользователя, перечислить что найдено и что нет, и отдельно искать оставшиеся товары.

## Pitfalls

- **External brands**: Products from brands like Агуша, Мираторг, Parmalat, Экологика, Бондюэль may not be in Vkusvill's catalog. Search may return Vkusvill-branded alternatives instead. If the exact product isn't found, tell the user and don't substitute — the user needs to find the xml_id manually.
- **Size variants**: Search may return a different size/weight variant first (e.g. 500 г vs 190 г). Always verify the name matches the user's request before adding.
- **Duplicate handling**: `add_product()` merges keys for existing xml_ids — no error, just keys_added=0.