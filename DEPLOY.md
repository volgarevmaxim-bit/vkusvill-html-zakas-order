# VkusVill Cart Server — деплой

**5-минутная установка на чистый VPS (Ubuntu 22.04/24.04).**

## Что делает

Минимальный веб-сервис: поле ввода списка продуктов → ссылка на корзину ВкусВилл.

Три шага внутри:
1. **Матчинг** (локальный, Python stdlib) — «нарзан» → xml_id 56160
2. **MCP API ВкусВилл** — создание ссылки на корзину через `vkusvill_cart_link_create`
3. **HTML-фронт** — одна страница, открывается в браузере телефона/ПК

## Требования к серверу

| Ресурс | Минимум |
|---|---|
| CPU | 1 vCPU |
| RAM | 256 MB (уложится в 128 после старта) |
| Диск | ~50 MB (проект весит <100 КБ + venv ~30 MB) |
| Python | 3.10+ |
| Сеть | Исходящий HTTPS к `mcp001.vkusvill.ru:443` |

## Быстрый деплой (5 минут)

```bash
# 1. Заходим на сервер
ssh root@<VPS_IP>

# 2. Системные пакеты
apt update && apt install -y python3 python3-venv python3-pip

# 3. Копируем проект (любым способом)
# Вариант А — scp с локальной машины:
#   scp -r vkusvill-server/ root@<VPS_IP>:/opt/vkusvill-server
# Вариант Б — git clone (если залито в репо)

# 4. Создаём venv и ставим зависимости
cd /opt/vkusvill-server
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 5. Запускаем
python app.py --port 8080
# Открываем http://<VPS_IP>:8080
```

## Systemd (автозапуск)

```bash
cat > /etc/systemd/system/vkusvill-cart.service << 'EOF'
[Unit]
Description=VkusVill Cart Server
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/vkusvill-server
ExecStart=/opt/vkusvill-server/venv/bin/gunicorn -w 2 -b 0.0.0.0:8080 app:app
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now vkusvill-cart
```

## Nginx reverse proxy (опционально)

```bash
apt install -y nginx

cat > /etc/nginx/sites-available/vkusvill << 'EOF'
server {
    listen 80;
    server_name _;  # заменить на домен при наличии
    client_max_body_size 1m;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
EOF

ln -sf /etc/nginx/sites-available/vkusvill /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx
```

## Структура проекта

```
vkusvill-server/
├── app.py                  # Flask-сервер (255 строк)
├── mcp_client.py           # JSON-RPC клиент к MCP ВкусВилл
├── requirements.txt        # flask, gunicorn
├── skills/                 # Локальные матчеры (vendored)
│   ├── vkusvill-quick-order/
│   │   ├── products.csv    # 52 товара с алиасами
│   │   └── scripts/resolver.py
│   └── vkusvill-smart-cart/
│       └── scripts/
│           ├── match.py    # 3-этапный матчинг
│           ├── embed.py    # Менеджер prefs
│           └── benchmark.py
├── vkusvill_prefs.json     # 54 товара v2
├── static/                 # (пустая, фронт вшит в app.py)
└── DEPLOY.md               # Этот файл
```

## API

### `POST /api/resolve`
```json
// Запрос
{"items": ["нарзан", "сырники", "бефстроганов"]}

// Ответ (успех)
{
  "url": "https://vkusvill.ru/cart/abc123...",
  "matches": [
    {"query": "нарзан", "xml_id": 56160, "name": "Вода минеральная...", "stage": "alias", "q": 1}
  ],
  "matched": 3,
  "unmatched": []
}

// Ответ (offline — MCP недоступен, только матчинг)
{
  "url": null,
  "matches": [...],
  "matched": 3,
  "unmatched": [...],
  "cart_error": "MCP недоступен: HTTP Error 403...",
  "offline": true
}
```

### `GET /health`
```json
{"ok": true}
```

## Обновление prefs

Добавить товар в локальный кеш:

```bash
cd /opt/vkusvill-server
source venv/bin/activate
python -c "
import sys; sys.path.insert(0, 'skills/vkusvill-smart-cart/scripts')
from embed import add_product
add_product(xml_id=12345, name='Новый товар', keys=['ключ1', 'ключ2'])
"
systemctl restart vkusvill-cart
```

## Безопасность

- Нет авторизации (рассчитано на закрытую сеть / друзей)
- При публичном доступе — поставить basic auth в nginx или VPN
- MCP-эндпоинт не кеширует чувствительные данные
- Все зависимости — чистый Python stdlib + flask (без compiled extensions)
