/**
 * Cloudflare Worker — прокси к MCP ВкусВилла для статической страницы.
 *
 * Зачем: mcp.vkusvill.ru отвечает 401 на preflight OPTIONS (Qrator WAF),
 * поэтому браузер не может вызвать его напрямую с GitHub Pages.
 * Воркер принимает запрос от страницы, добавляет CORS и ходит на MCP сам.
 *
 * Деплой (нужен бесплатный аккаунт Cloudflare):
 *   npm i -g wrangler && wrangler login
 *   wrangler deploy proxy/worker.js --name vv-mcp-proxy --compatibility-date 2026-01-01
 * Получится https://vv-mcp-proxy.<аккаунт>.workers.dev
 * Дальше страница: ...?proxy=https://vv-mcp-proxy.<аккаунт>.workers.dev
 */
const UPSTREAM = 'https://mcp.vkusvill.ru/mcp';
const ALLOWED = ['https://volgarevmaxim-bit.github.io'];

export default {
  async fetch(request) {
    const origin = request.headers.get('Origin') || '';
    const allow = ALLOWED.includes(origin) ? origin : ALLOWED[0];
    const cors = {
      'Access-Control-Allow-Origin': allow,
      'Access-Control-Allow-Methods': 'POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, Accept',
      'Access-Control-Max-Age': '86400',
    };
    if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: cors });
    if (request.method !== 'POST') {
      return new Response(JSON.stringify({ error: 'POST only' }), {
        status: 405, headers: { ...cors, 'Content-Type': 'application/json' },
      });
    }
    const body = await request.arrayBuffer();
    const upstream = await fetch(UPSTREAM, {
      method: 'POST',
      body,
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json, text/event-stream',
      },
    });
    return new Response(upstream.body, {
      status: upstream.status,
      headers: {
        ...cors,
        'Content-Type': upstream.headers.get('Content-Type') || 'application/json',
      },
    });
  },
};
