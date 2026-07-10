---
name: vkusvill-quick-order
description: "Fast-path VkusVill product resolver — normalize → exact → aliases → fuzzy → fallback."
version: 1.0.0
---

# VkusVill Quick Order

Fast-path product resolver. Use this **first** — it's local, instant, zero-token. Only fall back to `vkusvill-smart-cart` when `resolve()` returns `None`.

## Data store

`products.csv` — flat table with columns:

| Field | Description |
|---|---|
| `canonical_name` | Full product name from VkusVill catalog |
| `product_id` | VkusVill `xml_id` (integer) |
| `aliases` | Pipe-separated shortcut names (primary matching surface) |

To add a product: append a row to `products.csv`. Format: `canonical_name,product_id,alias1|alias2|alias3`.

## Matching pipeline

All stages run in Python via `execute_code`. **Never do matching in the LLM context.**

```
User query
    ↓
Normalize (lower, strip quotes, collapse spaces)
    ↓
Stage 1: Exact match on canonical_name
    ↓ (no match)
Stage 2: Exact match on any alias
    ↓ (no match)
Stage 3: Simple fuzzy — normalized Levenshtein ≤ 0.20
    ↓ (no match)
Stage 4: Log to ~/.hermes/vkusvill_unresolved.log → return None → FALLBACK
```

### How to call

```python
import sys
sys.path.insert(0, "~/.hermes/skills/vkusvill-quick-order/scripts")
from resolver import resolve

result = resolve("нарзан")
# → {"product_id": 56160, "canonical_name": "Вода минеральная 'Нарзан'...", "stage": "alias"}
```

If `result` is `None`, load `vkusvill-smart-cart` and run its pipeline.

### Batch resolve

```python
from resolver import resolve_all

result = resolve_all(["нарзан", "сырники", "чего-то-нет"])
# → {
#     "resolved": [{"query": "нарзан", "product_id": 56160, ...}, ...],
#     "unresolved": ["чего-то-нет"]
#   }
```

## Adding products to cart

Once resolved, use `vkusvill_cart_link_create` MCP tool:

```python
# Single product
result = resolve("нарзан")
if result:
    # → call vkusvill_cart_link_create with [{"xml_id": result["product_id"], "q": 1}]

# Batch
result = resolve_all(["нарзан", "сырники", "бефстроганов"])
cart_items = [
    {"xml_id": r["product_id"], "q": 1}
    for r in result["resolved"]
]
# → call vkusvill_cart_link_create with cart_items
```

Unresolved items go through the `vkusvill-smart-cart` fallback pipeline (search → match → offer to save).

## Logging

Unresolved queries are appended to `~/.hermes/vkusvill_unresolved.log`:

```
2026-05-15T17:43:00Z | "агуша творожок"
```

Use this to identify products that need adding to `products.csv`.

## Adding new products

Two ways:

1. **Quick** — append to `products.csv`:
   ```
   Пицца Маргарита, 350 г,123456,пицца маргарита|маргарита|пицца
   ```

2. **With search** — use `vkusvill-smart-cart` fallback to search, find xml_id, then add.

Always add at least 2-3 aliases covering different word orders.

## Pitfalls

- **Always try this skill first** — it's instant and costs zero tokens. Only fall back when needed.
- **Aliases are the primary matching surface** — make them good. Cover common shorthands, different word orders, common misspellings.
- **Fuzzy threshold is tight (0.20)** — it catches typos like "нaрзан" → "нарзан" but won't match unrelated products.
- **Unresolved log is append-only** — review it periodically and add missing products.
- **This skill does NOT search VkusVill API** — it only matches against `products.csv`. For unknown products, fall back to `vkusvill-smart-cart` which will search via `vkusvill_products_search`.
- **CSV encoding is UTF-8** — always write with utf-8 encoding.
- **Never substitute** — if fuzzy matches an unintended product, check `distance` field. If > 0.10, confirm with the user.
- **Multi-product queries**: `resolve()` принимает один товар за раз. Если пользователь пишет несколько товаров слитно (напр. «Нарзан Шишкин лес 400 мл»), сперва разбей запрос на отдельные товары (по смысловым границам) и вызывай `resolve_all()` с массивом. Если один из товаров не разрешился — уточни у пользователя, не пытайся угадать.
