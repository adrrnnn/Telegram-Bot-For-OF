/**
 * Cloudflare Worker - Telegram Bot API Key Management
 * 
 * Deploy this to Cloudflare Workers to securely manage bot credentials
 * 
 * Setup:
 * 1. Create a new Worker at https://dash.cloudflare.com
 * 2. Replace this code with the content below
 * 3. Set environment variables (see sec. 4 - add wrangler.toml bindings)
 * 4. Deploy the worker
 * 5. Copy the worker URL and add to bot config
 */

// Environment variables (set in wrangler.toml or Cloudflare dashboard)
export default {
  async fetch(req, env, ctx) {
    const url = new URL(req.url);
    const path = url.pathname;

    // Require authentication token in requests
    const authToken = req.headers.get('Authorization')?.replace('Bearer ', '').trim();
    if (!env.BOT_AUTH_TOKEN) {
      return new Response(
        JSON.stringify({
          error: 'Worker configuration error',
          details: 'BOT_AUTH_TOKEN not set in worker environment variables',
        }),
        { status: 500, headers: { 'Content-Type': 'application/json' } },
      );
    }
    if (authToken !== env.BOT_AUTH_TOKEN) {
      return new Response('Unauthorized', { status: 401 });
    }

    // Endpoint: GET /api/keys - Returns all configured API keys
    if (path === '/api/keys' && req.method === 'GET') {
      return new Response(
        JSON.stringify({
          gemini_key: env.GEMINI_API_KEY || null,
          openai_key: env.OPENAI_API_KEY || null,
          timestamp: new Date().toISOString(),
        }),
        { 
          headers: { 
            'Content-Type': 'application/json',
            'Cache-Control': 'no-cache, no-store, must-revalidate'
          } 
        }
      );
    }

    // Endpoint: POST /api/keys - Update API keys (admin only)
    if (path === '/api/keys' && req.method === 'POST') {
      try {
        const body = await req.json();
        const adminToken = req.headers.get('X-Admin-Token');
        
        if (adminToken !== env.ADMIN_TOKEN) {
          return new Response('Admin token required', { status: 403 });
        }

        // In production, store these in Cloudflare KV Storage
        // For now, they must be set via environment variables
        return new Response(
          JSON.stringify({
            status: 'ok',
            message: 'Update via Cloudflare dashboard environment variables',
            note: 'Restart bot after updating keys'
          }),
          { headers: { 'Content-Type': 'application/json' } }
        );
      } catch (e) {
        return new Response('Invalid JSON', { status: 400 });
      }
    }

    // Endpoint: GET /health - Health check
    if (path === '/health' && req.method === 'GET') {
      return new Response(
        JSON.stringify({ status: 'ok', timestamp: new Date().toISOString() }),
        { headers: { 'Content-Type': 'application/json' } }
      );
    }

    // 404 - Not found
    return new Response('Not found', { status: 404 });
  },
};
