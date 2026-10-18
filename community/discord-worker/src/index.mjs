/** Cloudflare Workers Discord Interaction endpoint; no long-running Gateway needed. */
const encoder = new TextEncoder();
const API = 'https://discord.com/api/v10';
const ADMIN = new Set(['post', 'channel', 'forum', 'thread']);

function bytes(hex) {
  if (!/^(?:[0-9a-f]{2})+$/i.test(hex)) throw new Error('Invalid hex');
  return Uint8Array.from(hex.match(/../g), n => parseInt(n, 16));
}
export async function verifyRequest(request, raw, publicKey, now = Date.now()) {
  const sig = request.headers.get('X-Signature-Ed25519') || '';
  const stamp = request.headers.get('X-Signature-Timestamp') || '';
  const seconds = Number(stamp);
  if (!/^\d{10,}$/.test(stamp) || !Number.isFinite(seconds) || Math.abs(now - seconds * 1000) > 300000) return false;
  try {
    const key = await crypto.subtle.importKey('raw', bytes(publicKey), { name: 'Ed25519' }, false, ['verify']);
    return await crypto.subtle.verify('Ed25519', key, bytes(sig), encoder.encode(stamp + raw));
  } catch { return false; }
}
function json(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json; charset=utf-8' } });
}
const reply = content => ({ type: 4, data: { content, flags: 64, allowed_mentions: { parse: [] } } });
const deferred = () => ({ type: 5, data: { flags: 64 } });
const optionsObject = opts => Object.fromEntries((opts || []).map(x => [x.name, x.value]));
const validChannel = s => typeof s === 'string' && /^[a-z0-9][a-z0-9-]{1,79}$/.test(s);
const validText = (s, max) => typeof s === 'string' && !!s.trim() && s.length <= max;
const authorized = (user, env) => (env.OPERATOR_IDS || '').split(',').map(x => x.trim()).includes(user);

async function api(env, method, path, body) {
  const r = await fetch(`${API}${path}`, {
    method, headers: { Authorization: `Bot ${env.DISCORD_TOKEN}`, 'Content-Type': 'application/json' },
    ...(body === undefined ? {} : { body: JSON.stringify(body) })
  });
  if (!r.ok) throw new Error(`Discord API ${r.status}`);
  return r.status === 204 ? null : r.json();
}
async function getChannel(env, id, type = 0) {
  if (typeof id !== 'string' || !/^\d{16,22}$/.test(id)) throw new Error('Invalid channel');
  const target = await api(env, 'GET', `/channels/${id}`);
  if (target.guild_id !== env.GUILD_ID || target.type !== type) throw new Error('Channel outside Lightning or wrong type');
  return target;
}
export async function act(i, env) {
  const opts = i.data?.options?.[0];
  const name = opts?.name;
  const args = optionsObject(opts?.options);
  const user = i.member?.user?.id || i.user?.id;
  if (!name || !['ping', 'post', 'channel', 'forum', 'thread', 'feedback'].includes(name)) return 'Unknown command.';
  if (ADMIN.has(name) && !authorized(user, env)) return 'Only the designated Lightning operator can do that.';
  try {
    if (name === 'ping') return 'Lightning Bot is responding.';
    if (name === 'post') {
      if (!validText(args.message, 1900)) return 'Message must have 1–1900 characters.';
      await getChannel(env, args.channel);
      await api(env, 'POST', `/channels/${args.channel}/messages`, { content: args.message.trim(), allowed_mentions: { parse: [] } });
      return `Posted in <#${args.channel}>.`;
    }
    if (name === 'channel' || name === 'forum') {
      if (!validChannel(args.name)) return 'Use a lowercase channel name (2–80 letters, numbers or hyphens).';
      if (typeof args.topic === 'string' && args.topic.length > 1024) return 'Topic is too long.';
      const target = await api(env, 'POST', `/guilds/${env.GUILD_ID}/channels`, { name: args.name, type: name === 'forum' ? 15 : 0, topic: args.topic || '' });
      return `Created <#${target.id}>.`;
    }
    if (name === 'thread') {
      if (!validText(args.name, 100) || !validText(args.message, 1900)) return 'Invalid thread title or opening message.';
      await getChannel(env, args.channel);
      const target = await api(env, 'POST', `/channels/${args.channel}/threads`, { name: args.name.trim(), type: 11, auto_archive_duration: 1440 });
      try {
        await api(env, 'POST', `/channels/${target.id}/messages`, { content: args.message.trim(), allowed_mentions: { parse: [] } });
      } catch { return `Created <#${target.id}>, but could not post the opening message. Check permissions.`; }
      return `Created thread <#${target.id}>.`;
    }
    if (name === 'feedback') {
      if (!env.FEEDBACK_CHANNEL_ID) return 'Feedback channel has not been configured.';
      if (!validText(args.topic, 100) || !validText(args.details, 1600)) return 'Invalid feedback topic or details.';
      await getChannel(env, env.FEEDBACK_CHANNEL_ID);
      await api(env, 'POST', `/channels/${env.FEEDBACK_CHANNEL_ID}/messages`, {
        embeds: [{ title: args.topic.trim(), description: args.details.trim(), footer: { text: `Discord user ID: ${user}` } }],
        allowed_mentions: { parse: [] }
      });
      return 'Feedback received by the Lightning team.';
    }
  } catch (error) {
    console.error('Discord operation failed:', error.message);
    return 'Discord could not complete the request. Check bot permissions and configuration.';
  }
  return 'Unsupported command.';
}
async function finish(i, env) {
  const msg = await act(i, env);
  const url = `${API}/webhooks/${env.APP_ID}/${i.token}/messages/@original`;
  const r = await fetch(url, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content: msg, allowed_mentions: { parse: [] } })
  });
  if (!r.ok) console.error('Could not update Discord interaction:', r.status);
}
export async function handle(request, env, context) {
  const url = new URL(request.url);
  if (url.pathname !== '/interactions' || request.method !== 'POST') return new Response('Not found', { status: 404 });
  if (!env.PUBLIC_KEY || !env.GUILD_ID || !env.APP_ID || !env.DISCORD_TOKEN || !env.OPERATOR_IDS) return new Response('Not configured', { status: 503 });
  const raw = await request.text();
  if (!(await verifyRequest(request, raw, env.PUBLIC_KEY))) return new Response('Invalid signature', { status: 401 });
  let i;
  try { i = JSON.parse(raw); } catch { return new Response('Invalid JSON', { status: 400 }); }
  if (i.type === 1) return json({ type: 1 });
  if (i.type !== 2) return json(reply('Unsupported interaction.'));
  if (i.guild_id !== env.GUILD_ID || i.application_id !== env.APP_ID) return json(reply('This application is only for the Lightning server.'));
  if (!i.token || !i.data?.options?.length) return json(reply('Invalid command.'));
  context.waitUntil(finish(i, env).catch(error => console.error("Interaction completion failed:", error?.message)));
  return json(deferred());
}
export default { fetch: handle };
