/**
 * Cloudflare Worker - Telegram Bot API Key Management (FIXED)
 * Properly handles environment variables and auth tokens
 */
export default {
  async fetch(req, env, ctx) {
    const url = new URL(req.url);
    const path = url.pathname;

    // Debug endpoint - no auth required (for testing without auth)
    if (path === '/debug' && req.method === 'GET') {
      return new Response(
        JSON.stringify({
          message: 'Worker is running',
          env_check: {
            has_gemini_key: !!env.GEMINI_API_KEY,
            has_openai_key: !!env.OPENAI_API_KEY,
            has_bot_auth_token: !!env.BOT_AUTH_TOKEN,
            bot_auth_token_length: env.BOT_AUTH_TOKEN ? env.BOT_AUTH_TOKEN.length : 0,
          },
          timestamp: new Date().toISOString(),
        }),
        { 
          headers: { 
            'Content-Type': 'application/json',
            'Cache-Control': 'no-cache'
          } 
        }
      );
    }

    // Health check - no auth required
    if (path === '/health' && req.method === 'GET') {
      return new Response(
        JSON.stringify({ status: 'ok', timestamp: new Date().toISOString() }),
        { headers: { 'Content-Type': 'application/json' } }
      );
    }

    // Get auth token from header
    const authHeader = req.headers.get('Authorization');
    const authToken = authHeader ? authHeader.replace('Bearer ', '').trim() : null;

    // Validate environment variables are set
    if (!env.BOT_AUTH_TOKEN) {
      return new Response(
        JSON.stringify({ 
          error: 'Worker configuration error',
          details: 'BOT_AUTH_TOKEN not set in worker environment variables'
        }),
        { 
          status: 500, 
          headers: { 'Content-Type': 'application/json' } 
        }
      );
    }

    // Check authentication token
    if (!authToken) {
      return new Response(
        JSON.stringify({ error: 'Missing Authorization header' }),
        { 
          status: 401, 
          headers: { 'Content-Type': 'application/json' } 
        }
      );
    }

    if (authToken !== env.BOT_AUTH_TOKEN) {
      return new Response(
        JSON.stringify({ error: 'Invalid authentication token' }),
        { 
          status: 401, 
          headers: { 'Content-Type': 'application/json' } 
        }
      );
    }

    // Endpoint: GET /api/keys - Returns all configured API keys (requires auth)
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

    // 404 - Not found
    return new Response('Not found', { status: 404 });
  },
};
