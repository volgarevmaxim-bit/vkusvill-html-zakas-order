# VkusVill Cart Server — HANDOFF

**Последняя сессия:** 2026-07-10 (vkusvill-selector: 2026-07-10 19:39–19:45)  
**Сервер:** vps1-RU / Delanie — 135.106.153.41 (Ubuntu 24.04)  
**SSH:** `ssh -i /opt/data/vpn-agent-bench/secrets/vpn-bench-ed25519 root@135.106.153.41`

## Состояние сервера

| Компонент | Статус |
|---|---|
| Проект | `/opt/vkusvill-server/` — все файлы на месте |
| venv | Python 3.12.3, flask 3.1.3, gunicorn 26.0.0 |
| systemd | `vkusvill-cart.service` — active, enabled, автозапуск |
| Порт | 0.0.0.0:8080 (gunicorn -w 2) |
| Nginx | ✅ настроен — порт 80, basic auth → proxy_pass 127.0.0.1:8080 |
| URL | `https://vv.vedomir.ru` (HTTP → HTTPS редирект) |

## API (работает)

- `GET /health` → `{"ok":true}`
- `POST /api/resolve` — полный пайплайн: items → матчинг → корзина
- `POST /api/match` — только локальный матчинг одного запроса
- `POST /api/cart` — создание корзины по xml_id
- `GET /` — HTML-фронтенд

## Этапы матчинга

1. **quick-order** (alias-матчер, 52 товара в `products.csv`) — мгновенный, без токенов
2. **smart-cart** (`match_all`) — трёхэтапный (substring → Левенштейн → триграммы)
3. **MCP ВкусВилл** — `vkusvill_cart_link_create` для создания корзины

## Исправленные баги (2026-07-10)

### 1. `/root/.hermes/` не существует
`resolver.py:144` пишет лог в `/root/.hermes/vkusvill_unresolved.log`.  
Директории не было → `FileNotFoundError` → 500 на `/api/resolve`.  
**Fix:** `mkdir -p /root/.hermes` (сделано на сервере).

### 2. Qrator блокирует urllib (MCP 403)
`urllib.request` по умолчанию шлёт `User-Agent: Python-urllib/3.x`.  
Qrator WAF на `mcp001.vkusvill.ru` блокирует такие запросы.  
**Fix:** Добавлен `User-Agent: VkusVill-Cart-Server/1.0` в `mcp_client.py:18`.

### 3. create_cart_link не парсит data.link
MCP возвращает `{"ok": true, "data": {"link": "https://..."}}`.  
Код искал `url`/`link` только на верхнем уровне, а не внутри `data`.  
**Fix:** Добавлен обход `parsed["data"]["link"]` + обработка `ok: false` как исключения.

### 4. JS split('\\n') → SyntaxError (2026-07-10)
В Python `"""..."""` строке `'\\n'` превращается в literal newline (0x0A), а не `\n` (backslash+n).  
JS-скрипт падал с SyntaxError на строке `q.split('\n')` → кнопка не работала.  
**Fix:** `q.split('\\n')` → `q.split(String.fromCharCode(10))` — без бэкслешей, без конфликта с Python-эскейпингом.  
Также добавлен `q.replace(/,/g, String.fromCharCode(10))` — поддержка запятых как разделителей.

### 5. match.py читал не тот prefs.json (2026-07-10)

## Локальный репозиторий

**Путь:** `/opt/data/vkusvill-server/` (C:\vkusvill-server на Windows-хосте)

Три файла изменены относительно исходного деплоя:
- `mcp_client.py` — User-Agent + парсинг data.link + обработка ошибок
- `app.py` — без изменений (как на сервере)

## Что НЕ сделано / на будущее

### ✅ TLS / HTTPS (2026-07-10)
- Домен: `vv.vedomir.ru` → A 135.106.153.41
- Сертификат: Let's Encrypt (авто-продление)
- Nginx stream SNI-роутинг на 443: `vv.vedomir.ru` → HTTPS 8443, всё остальное → xray 8444
- HTTP (80): редирект на HTTPS

### ✅ Устаревшие xml_id (почищены 2026-07-10)

Удалены 4 несуществующих xml_id:
- 64201 — Сырники творожные, 260 г
- 50459 — Пирожное "Шоколадный Микс"
- 117213 — Томаты Ташкентские сладкие, 400 г
- 118287 — Салат с капустой и огурцом

**Итого:** prefs.json 54→50, products.csv 52→48.


### ✅ Парсинг без запятых (2026-07-10)

Проблема: `нарзан сырники бефстроганов` (пробелы, без запятых) → один слипшийся запрос → матчился только нарзан.
Исправлено на двух уровнях:

1. **JS (app.py:98-102)**: split по `/[\n,]+/` + fallback: если 1 элемент с пробелами → split по `\s+`
2. **Python (app.py:196-208)**: сервер разбивает запросы с 3+ слов на отдельные слова (2 слова = возможное название товара, не разбиваем)
3. **Python (app.py:223-248)**: Stage 2b — если запрос не смэтчился и содержит пробелы, пробуем каждое слово отдельно

## checkpoint 2026-07-10 — фикс парсинга без запятых
- намерение: починить обработку ввода без запятых (пробелы как разделители)
- текущее состояние: сервер обновлён, все три сценария работают идентично
- следующий шаг: git commit в локальном репозитории ✅ (сделано 2026-07-10)

### ✅ Мониторинг (сделано 2026-07-10)

| Компонент | Детали |
|---|---|
| Health check | systemd timer каждые 5 мин → `healthcheck.sh` → curl /health |
| Логи ошибок | `journalctl -t vkusvill-health` |
| Logrotate | `/etc/logrotate.d/vkusvill` — daily, 7 ротаций, compress |
| Логи матчинга | `/root/.hermes/vkusvill*.log` — авто-ротация через logrotate |

Проверка: `systemctl status vkusvill-healthcheck.timer`

## Обновление кода на сервере

```bash
# Из локальной папки:
scp -i /opt/data/vpn-agent-bench/secrets/vpn-bench-ed25519 \
  /opt/data/vkusvill-server/mcp_client.py \
  root@135.106.153.41:/opt/vkusvill-server/

# Перезапуск:
ssh -i /opt/data/vpn-agent-bench/secrets/vpn-bench-ed25519 root@135.106.153.41 \
  'systemctl restart vkusvill-cart'
```

## Обновление prefs (добавление товаров)

```bash
ssh -i /opt/data/vpn-agent-bench/secrets/vpn-bench-ed25519 root@135.106.153.41
cd /opt/vkusvill-server
source venv/bin/activate
python -c "
import sys; sys.path.insert(0, 'skills/vkusvill-smart-cart/scripts')
from embed import add_product
add_product(xml_id=12345, name='Новый товар', keys=['ключ1', 'ключ2'])
"
systemctl restart vkusvill-cart
```

## Nginx (сделано 2026-07-10, обновлено 19:35)

| Компонент | Статус |
|---|---|
| Nginx | 1.24.0, `systemctl enable --now` |
| Порт 80 | 0.0.0.0:80 → 301 redirect на HTTPS |
| Порт 443 | stream SNI-роутинг → HTTPS 8443 / xray 8444 |
| HTTPS (внутр.) | 127.0.0.1:8443 → proxy_pass 127.0.0.1:8080 |
| Gunicorn | `127.0.0.1:8080` (не exposed) |
| Basic auth | `vv` / `8cZA5iB4WES7` |
| Сертификат | Let's Encrypt, авто-продление, до 2026-10-08 |
| Конфиг HTTP | `/etc/nginx/sites-available/vkusvill` |
| Конфиг stream | `/etc/nginx/stream.d/vkusvill-sni.conf` |
| htpasswd | `/etc/nginx/auth/vkusvill` |

Сменить пароль: `htpasswd -b /etc/nginx/auth/vkusvill vv <новый>` → `systemctl reload nginx`.

### ✅ Убран stage из UI (2026-07-10)
Технические метки (`substring_p2`, `alias`, `levenshtein`) больше не показываются в карточках товаров — только название. JS-шаблон в `app.py:110` убран `<span class="stage">`.

### ✅ Бэкап (v1: 2026-07-10, v2: 2026-07-10)
- Сервер: `/opt/vkusvill-server-backups/vkusvill-server-backup-20260710-1326.tar.gz` (v1, 6.4M), `...-20260710-1855.tar.gz` (v2, 2.4M)
- Локально: `/opt/data/vkusvill-server/backups/vkusvill-server-backup-20260710-1326.tar.gz` (v1), `...-20260710-1855.tar.gz` (v2)

### ✅ vkusvill-server-summary.md (2026-07-10)
Итоговый документ: как заходить, что сделано, извлечённые уроки.

## checkpoint 2026-07-10 19:35 — TLS / HTTPS через nginx SNI-роутинг
- намерение: поднять HTTPS на vv.vedomir.ru рядом с xray REALITY на 443
- что сделано: certbot + Let's Encrypt, nginx stream SNI-роутинг (vv.vedomir.ru → HTTPS 8443, остальное → xray 8444)
- текущее состояние: https://vv.vedomir.ru работает, сертификат валиден до 2026-10-08, авто-продление
- следующий шаг: git commit

## Проверка после перезагрузки сервера

```bash
ssh -i /opt/data/vpn-agent-bench/secrets/vpn-bench-ed25519 root@135.106.153.41 '
  systemctl is-active vkusvill-cart &&
  curl -s http://127.0.0.1:8080/health &&
  curl -s -X POST http://127.0.0.1:8080/api/resolve \
    -H "Content-Type: application/json" \
    -d "{\"items\":[\"нарзан\"]}" | python3 -m json.tool | grep -q share_basket && echo "OK"
'
```

## checkpoint 2026-07-10 14:30 — git init + HANDOFF cleanup
- намерение: закоммитить фикс парсинга + почистить HANDOFF от противоречий
- сделанное: git init, добавлены все файлы
- HANDOFF: убрано «Nginx НЕ настроен» (было противоречие со строкой 133),
  перенесён xml_id-список в секцию «Устаревшие xml_id»,
  чекпоинт прошлой сессии обновлён (git commit ✅)
- следующий шаг: ждать указаний пользователя

## checkpoint 2026-07-10 14:45 — системный фикс парсинга
- намерение: заменить три заплатки (JS fallback, 3+ слов, Stage 2b) на единый подход
- новый подход:
  1. JS: `split(/[\s,\n]+/)` — равномерно по всем разделителям
  2. Python Stage 0: каждый query разбивается на отдельные слова
  3. Python Stage 2b: join-проход — если слово не смэтчилось, пробуем склеить с соседом
- следующий шаг: git commit ✅ (сделано 2026-07-10)

## HTML5-селектор (vkusvill-selector.html)

Создан 2026-07-10 в отдельной сессии (19:39–19:45).  **Обновлён 2026-07-11 — прямой MCP, без сервера.**

**Файл:** `/opt/data/vkusvill-server/vkusvill-selector.html` (291 строка, 48 КБ)
**PWA:** `/opt/data/vkusvill-server/manifest.json` — для установки на телефон при хостинге через HTTPS

- **119 товаров** в 12 категориях (из `ВкусВилл_ЧастоЗаказываемые.csv` + `prefs.json`)
- **Полностью автономный** — не требует сервера, открывается на Android/iOS как файл
- **Прямой вызов MCP** — кнопка «Собрать корзину» шлёт JSON-RPC напрямую на `mcp001.vkusvill.ru/mcp`
  - `vv.vedomir.ru/api/cart` больше не нужен!
  - CORS: `Access-Control-Allow-Origin: *` — работает даже из `file://`
- Дерево категорий с раскрытием/сворачиванием (изначально все свёрнуты)
- Один товар может быть в нескольких категориях (168 листьев в дереве при 119 уникальных xml_id)
- Поиск с фильтрацией, выбор товаров индивидуально (без массового выбора категории)
- Выбор количества (1–40 на каждый товар)
- Кнопка «Собрать корзину» → прямой JSON-RPC `tools/call` → ссылка ВкусВилл
- Копирование ссылки в буфер обмена
- Тёмная тема, адаптивная вёрстка (max-width 600px)
- PWA: manifest.json, apple-mobile-web-app метатеги — устанавливается на домашний экран при хостинге через HTTPS

**Категории:** Бакалея, Готовая еда, Детское, Заморозка, Молочка, Мясо / Птица, Напитки, Овощи / Фрукты, Рыба, Сладости / Десерты, Хлеб / Выпечка, Хозтовары.

## checkpoint 2026-07-10 — vkusvill-selector.html создан, обновлены HANDOFF + summary

## checkpoint 2026-07-10 18:55 — JS regex fix + бэкап v2
- намерение: починить кнопку «Собрать корзину» (ничего не возвращала)
- корневая причина: в Python triple-quoted строке `\n` → real newline (0x0A).
  JS не разрешает переводы строк в regex-литерале → SyntaxError → doResolve undefined.
- fix: `\\\\n` (два бэкслеша) в исходнике → Python отдаёт `\\n` (бэкслеш+n) → JS ок.
- бэкап: v2 (20260710-1855, 2.4M) на сервере и локально. v1 (20260710-1326, 6.4M) сохранён.
- следующий шаг: ждать указаний пользователя

## checkpoint 2026-07-11 — прямой MCP в селекторе, PWA, без сервера
- намерение: сделать vkusvill-selector.html полностью независимым от vv.vedomir.ru/api/cart
- что сделано:
  1. Кнопка «Собрать корзину» теперь шлёт JSON-RPC напрямую на `mcp001.vkusvill.ru/mcp`
     — CORS `Access-Control-Allow-Origin: *` позволяет вызовы из `file://` и с любого origin
  2. Добавлен PWA manifest (`manifest.json`) + apple-mobile-web-app метатеги
     — селектор можно установить на домашний экран при хостинге через HTTPS
  3. Парсинг ответа MCP: `result.content[0].text → JSON.parse → data.link`
- текущее состояние: селектор полностью автономен, сервер не нужен для создания корзины
- серверный `/api/cart` продолжает работать (обратная совместимость)
- следующий шаг: ждать указаний пользователя

## checkpoint 2026-07-11 19:25 — быстрый ввод + матчинг в селекторе
- намерение: добавить текстовый ввод «нарзан йогурт мандарин» (без запятых) с авто-матчингом
- что сделано:
  1. **JS-движок матчинга** (чистый JS, без сервера):
     - Stage 1: alias-матчер (106 алиасов из quick-order `products.csv`)
     - Stage 2: substring-поиск по названиям 119 товаров (выбирает самое короткое имя)
     - Stage 3: word-level матчинг (токен совпадает с началом слова в названии)
     - Fallback: биграммы — склейка соседних токенов для многословных названий
  2. **Панель быстрого матча** — карточки с галочками под строкой поиска
     - Авто-выбор всех совпадений при вводе
     - Дедупликация по xml_id
     - Показ ненайденных токенов
  3. **Enter → фокус на кнопку корзины** — быстрый флоу: ввёл → Enter → Собрать
  4. При активном поиске дерево скрывается, показывается панель матчинга
  5. При очистке поиска (Сбросить) дерево возвращается
- бэкап: v4 (20260711-1925, 72K)
- коммит: 1823ad6
- следующий шаг: ждать указаний пользователя

## checkpoint 2026-07-11 — фикс авто-выбора + UI cleanup
- 93f0756: авто-выбор не накапливает мусор от промежуточных нажатий (`_autoSelected`)
- cdfd510: убраны qty-ряд (количество всегда 1), stage-метки на карточках, иконка поиска 🔍 (съезжала на Android/Edge), фикс скрытия «Ничего не найдено»
- следующий шаг: ждать указаний пользователя

## checkpoint 2026-07-11 20:18 — деплой на vv.vedomir.ru/select/ + PWA офлайн
- намерение: сделать селектор доступным для друзей по ссылке (Android/iPhone)
- что сделано:
  - **Nginx**: `/select/` → статические файлы из `/opt/vkusvill-server/selector/`, без basic auth
  - **Service Worker** (`sw.js`): кэширует index.html + manifest.json → офлайн после первого открытия
  - Файлы на сервере: `index.html` (58K), `manifest.json`, `sw.js` → права 644
  - `auth_basic` перенесён в `location /` — только API под паролем
- **URL для друзей:** `https://vv.vedomir.ru/select/` — без пароля, PWA-установка, офлайн-каталог
- следующий шаг: ждать указаний пользователя
