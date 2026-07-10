#!/bin/bash
# VkusVill Cart health check — вызывается systemd таймером каждые 5 минут
# Логирует ошибки в journald с тегом vkusvill-health

ENDPOINT="http://127.0.0.1/health"
AUTH="vv:8cZA5iB4WES7"

if ! curl -sf --max-time 10 -u "$AUTH" "$ENDPOINT" > /dev/null 2>&1; then
    EXIT_CODE=$?
    echo "HEALTH FAIL: curl exit=$EXIT_CODE on $ENDPOINT at $(date -Iseconds)" | systemd-cat -t vkusvill-health -p err
    exit 1
fi
