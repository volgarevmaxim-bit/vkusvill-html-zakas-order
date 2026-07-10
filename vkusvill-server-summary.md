# VkusVill Cart Server — итоговый обзор

**Дата:** 2026-07-10 (обновлено 18:55)  
**Сервер:** 135.106.153.41 (vps1-RU, Ubuntu 24.04)  
**Бэкапы:** `backups/` — v1 (13:26, 6.4M), v2 (18:55, 2.4M)

---

## Что это

Минимальный веб-сервис: вводишь список продуктов → получаешь ссылку на корзину ВкусВилл.
Одна HTML-страница, открывается в браузере телефона или ПК.

Три этапа внутри:
1. **quick-order** — мгновенный alias-матчер (48 товаров в `products.csv`), ноль токенов
2. **smart-cart** — трёхэтапный матчинг (substring → Левенштейн → триграммы), 50 товаров в `vkusvill_prefs.json`
3. **MCP ВкусВилл** — `vkusvill_cart_link_create` для создания ссылки на корзину

---

## Как заходить

### SSH
```bash
ssh -i /opt/data/vpn-agent-bench/secrets/vpn-bench-ed25519 root@135.106.153.41
```

### Проект на сервере
```
/opt/vkusvill-server/
```

### URL
```
http://135.106.153.41
```
Basic auth: `vv` / `8cZA5iB4WES7` (nginx).

### Локальная копия
```
/opt/data/vkusvill-server/   (он же C:\vkusvill-server на Windows-хосте)
```

---

## Состояние сервера

| Компонент | Статус |
|---|---|
| systemd (`vkusvill-cart.service`) | active, enabled, автозапуск |
| Gunicorn | 2 воркера, `127.0.0.1:8080` |
| Nginx | `0.0.0.0:80 → proxy_pass 127.0.0.1:8080`, basic auth |
| Health check | systemd timer каждые 5 мин → `/health` |
| Logrotate | daily, 7 ротаций, compress |
| Python | 3.12.3, flask 3.1.3, gunicorn 26.0.0 |
| Файрвол | не настроен (полагаемся на nginx + basic auth) |

### API

| Метод | Путь | Что делает |
|---|---|---|
| GET | `/` | HTML-фронтенд |
| GET | `/health` | `{"ok":true}` |
| POST | `/api/resolve` | items → матчинг → корзина |
| POST | `/api/match` | локальный матчинг одного запроса |
| POST | `/api/cart` | корзина по xml_id |

### Проверка после перезагрузки
```bash
ssh -i /opt/data/vpn-agent-bench/secrets/vpn-bench-ed25519 root@135.106.153.41 '
  systemctl is-active vkusvill-cart &&
  curl -s http://127.0.0.1:8080/health &&
  curl -s -X POST http://127.0.0.1:8080/api/resolve \
    -H "Content-Type: application/json" \
    -d "{\"items\":[\"нарзан\"]}" | python3 -m json.tool | grep -q share_basket && echo "OK"
'
```

---

## Что сделано

### Инфраструктура (сессия 2026-07-10)
- Nginx reverse proxy + basic auth (вместо голого gunicorn на 0.0.0.0)
- Gunicorn переключен на `127.0.0.1:8080` (не exposed наружу)
- Health check: systemd timer + `healthcheck.sh` каждые 5 минут
- Logrotate: daily ротация логов матчинга и системных
- Бэкап всего проекта на сервере и локально (v1), v2 после фикса JS + парсинга

### Баги (исправлено 5 штук)

1. **`/root/.hermes/` не существовал** — `resolver.py` падал с `FileNotFoundError` при попытке писать лог.  
   → `mkdir -p /root/.hermes`

2. **Qrator блокирует Python-urllib** — дефолтный `User-Agent: Python-urllib/3.x` отбрасывается WAF на `mcp001.vkusvill.ru`.  
   → Кастомный `User-Agent: VkusVill-Cart-Server/1.0` в `mcp_client.py`

3. **create_cart_link не парсил data.link** — MCP возвращает `{"ok":true, "data":{"link":"https://..."}}`, код искал `link` только на верхнем уровне.  
   → Обход `parsed["data"]["link"]` + обработка `ok:false`

4. **JS split('\\n') → SyntaxError** — Python-строка `"""..."""` превращала `'\\n'` в literal newline, ломая синтаксис JS-скрипта. Кнопка «Собрать корзину» молчала.  
   → `String.fromCharCode(10)` вместо `'\n'` + поддержка запятых как разделителей

5. **match.py читал не тот prefs.json** — жёсткий путь `/root/.hermes/vkusvill_prefs.json` (пустой) вместо `/opt/vkusvill-server/vkusvill_prefs.json`.  
   → `app.py` патчит `match.PREFS_PATH` на правильный

### Данные (сессия 2026-07-10)
- Удалены 4 устаревших xml_id (сырники, пирожное, томаты, салат) — товары удалены из каталога ВкусВилл
- prefs.json: 54 → 50 товаров, products.csv: 52 → 48 товаров

### UI (сессия 2026-07-10)
- Убраны технические метки (`substring_p2`, `alias`, `levenshtein`) из карточек товаров — теперь только название продукта

### Что не сделано
- **TLS / HTTPS** — сервер без домена, сертификат не настроен. При появлении домена: Let's Encrypt + certbot
- **Файрвол (ufw/iptables)** — не настроен. Пока достаточно nginx + basic auth

---

## Извлечённые уроки

### 1. Python triple-quoted strings ≠ JavaScript strings
Когда JS-код вшит в Python `"""..."""`, бэкслеш-последовательности интерпретируются Python-парсером. `'\\n'` в Python-строке превращается в literal newline (0x0A), а не в `\n` (backslash+n). Решение — избегать бэкслешей в JS внутри Python: `String.fromCharCode(10)`.

### 2. MCP-клиент должен парсить вложенные поля
MCP ВкусВилл заворачивает `link` внутрь `{"ok": true, "data": {"link": "..."}}`, а не кладёт на верхний уровень. Код, написанный «по документации», может искать не там. Всегда проверяй реальный JSON-ответ, а не спецификацию.

### 3. User-Agent имеет значение для WAF
Qrator (и аналоги) блокируют запросы с дефолтными Python/curl User-Agent. Кастомный `User-Agent` с человекочитаемым именем — дешёвый способ обойти WAF без прокси.

### 4. Жёсткие пути ломаются при деплое
`Path.home() / ".hermes"` на сервере = `/root/.hermes/`, а не `/opt/vkusvill-server/`. Навыки (skills) написаны для Hermes Agent и используют `Path.home()`; при деплое на standalone-сервер нужно monkey-patch пути. Паттерн: `import match as _match; _match.PREFS_PATH = HERE / "vkusvill_prefs.json"`.

### 5. Валидация xml_id — не разовая операция
Товары удаляются из каталога ВкусВилл со временем. 4 из ~54 товаров исчезли за несколько месяцев. Нужна периодическая проверка: прогонять все xml_id через `vkusvill_cart_link_create` и удалять отвалившиеся.

### 6. HANDOFF.md требует ручной чистки
После нескольких сессий HANDOFF накапливает противоречия: секция «Что НЕ сделано» говорит «nginx не настроен», а секция ниже — «nginx сделан». Нужно периодически вычитывать и удалять устаревшие блоки.

### 7. Бэкап с версионностью — не перезаписывать старый
`tar czf` с датой-временем в имени файла = 10 секунд. Никогда не перезаписывать предыдущий бэкап — держать рядом v1, v2, ... Хранить в отдельной подпапке (`backups/`), не в корне проекта. Копировать и на сервер, и локально. Откат = `tar xzf backups/нужная_версия.tar.gz`.

### 8. Фронтенд не должен показывать внутренние детали матчинга
Пользователю не нужны `substring_p2`, `levenshtein`, `alias` — только название товара. Технические поля пусть остаются в API для отладки, но на UI — только name.

### 9. Тестировать в браузере после каждого деплоя, не только curl
curl подтверждает, что API жив, но не ловит битый JS. После деплоя открыть страницу в браузере, нажать кнопку — только так видно, что скрипт загрузился и работает. `\n` в Python triple-quoted строке стал real newline → JS regex literal сломан → `doResolve undefined` → кнопка молчит. curl показал бы `200 OK`.

### 10. Системное решение вместо заплаток — экономит время на втором баге
Три эвристики (JS fallback для 1 элемента, Python 3+ слов, Stage 2b) покрывали часть случаев, но не «йогурт, нарзан мандарины». Единый подход (split по всем разделителям + join-проход с проверкой xml_id) покрыл все случаи сразу. Вторая сессия на латание дыр заняла бы столько же, сколько первая — но системный фикс закрыл класс проблем, а не один кейс.
