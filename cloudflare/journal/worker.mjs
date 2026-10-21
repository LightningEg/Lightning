/* Opaque journal delivery. Financial validation and decryption stay on devices. */
const DAY = 86400000;
const ENVELOPE = 65536;
const CHUNK = 32768;
const SNAPSHOT = 200 * 1024 * 1024;
// Each profile gets this many sync requests a month (UTC). Over it, sync waits for next month and the local link
// still works. Registry and membership calls have their own small allowance, so recovery is never locked out.
// Checkpoint chunks (first pairing or repair over the internet) count apart, so one copy cannot use up a month of sync.
const MONTHLY = {sync:['MONTHLY_REQUESTS', 1500], snapshot:['MONTHLY_SNAPSHOT_REQUESTS', 4000], control:[null, 200]};
function monthly(env, bucket) {
  const [name, fallback] = MONTHLY[bucket], value = name ? Number(env[name] ?? fallback) : fallback;
  return Number.isSafeInteger(value) && value >= 0 ? value : fallback;
}
const encoder = new TextEncoder();
export function canonical(value) {
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
  if (value !== null && typeof value === 'object') return '{' + Object.keys(value).sort().map(k => JSON.stringify(k) + ':' + canonical(value[k])).join(',') + '}';
  return JSON.stringify(value);
}
const hex = bytes => [...new Uint8Array(bytes)].map(x => x.toString(16).padStart(2, '0')).join('');
const unhex = s => Uint8Array.from(s.match(/../g) || [], x => parseInt(x, 16));
const hash = async value => hex(await crypto.subtle.digest('SHA-256', typeof value === 'string' ? encoder.encode(value) : value));
const id = value => typeof value === 'string' && /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/.test(value);
const digest = value => typeof value === 'string' && /^[0-9a-f]{64}$/.test(value);
function require(condition, status = 400) { if (!condition) throw Object.assign(new Error('Refused'), {status}); }
function json(value, status = 200) { return Response.json(value, {status, headers: {'Cache-Control': 'no-store'}}); }
async function read(request, limit = 96 * 1024) {
  require(!request.headers.get('Content-Encoding'));
  const reader = request.body?.getReader();
  if (!reader) return new Uint8Array();
  let size = 0, parts = [];
  while (true) {
    const {value, done} = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > limit) { await reader.cancel(); require(false, 413); }
    parts.push(value);
  }
  const bytes = new Uint8Array(size); let offset = 0;
  for (const part of parts) { bytes.set(part, offset); offset += part.byteLength; }
  return bytes;
}
function parse(bytes) {
  const text = new TextDecoder('utf-8', {fatal: true}).decode(bytes);
  const data = JSON.parse(text);
  require(canonical(data) === text); // Also rejects repeated keys and noncanonical numbers.
  return data;
}
export async function verify(key, body, signature) {
  if (typeof key !== 'string' || !/^04[0-9a-f]{128}$/.test(key) || typeof signature !== 'string' || !/^[0-9a-f]{128}$/.test(signature)) return false;
  try {
    const publicKey = await crypto.subtle.importKey('raw', unhex(key), {name:'ECDSA', namedCurve:'P-256'}, false, ['verify']);
    return await crypto.subtle.verify({name:'ECDSA', hash:'SHA-256'}, publicKey, unhex(signature), encoder.encode(canonical(body)));
  } catch (_) { return false; }
}

export default {
  async fetch(request, env) {
    try {
      require(env.DEPLOYMENT_POLICY === 'free-only', 503);
      const url = new URL(request.url);
      const match = /^\/profiles\/([0-9a-f-]{36})(\/.*)$/.exec(url.pathname);
      require(match && id(match[1]) && !url.search, 404);
      // The object chooses its profile once during authenticated provisioning.
      return await env.PROFILES.get(env.PROFILES.idFromName(match[1])).fetch(request);
    } catch (error) { return json({error:'request refused'}, error.status || 400); }
  }
};

export class ProfileMailbox {
  constructor(state, env) { this.state = state; this.storage = state.storage; this.env = env; }
  async fetch(request) {
    try {
      require(this.env.DEPLOYMENT_POLICY === 'free-only', 503);
      const url = new URL(request.url), [, profile, route] = /^\/profiles\/([0-9a-f-]{36})(\/.*)$/.exec(url.pathname) || [];
      require(id(profile) && !url.search, 404);
      const bytes = await read(request);
      if (route === '/provision') return await this.provision(request, profile, bytes);
      const auth = await this.authenticate(request, profile, route, bytes);
      if (route === '/wake') return this.wake(auth, request);
      if (route === '/push-token') return await this.pushToken(auth, parse(bytes));
      if (route === '/send') return await this.send(auth, parse(bytes));
      if (route === '/receive') return await this.receive(auth);
      if (route === '/ack') return await this.ack(auth, parse(bytes));
      if (route === '/snapshot/start') return await this.startSnapshot(auth, parse(bytes));
      if (route === '/snapshot/put') return await this.putChunk(auth, parse(bytes));
      if (route === '/snapshot/get') return await this.getChunk(auth, parse(bytes));
      if (route === '/snapshot/status') return await this.snapshotStatus(auth, parse(bytes));
      if (route === '/snapshot/finish') return await this.finishSnapshot(auth, parse(bytes));
      if (route === '/authority') return json(auth.registry);
      if (route === '/authority/chain') return await this.authorityChain(auth,parse(bytes));
      if (route === '/authority/transition') return await this.transition(auth, parse(bytes));
      if (route === '/membership') return await this.membership(auth, parse(bytes));
      if (route === '/membership/update') return await this.membershipUpdate(auth, parse(bytes));
      require(false, 404);
    } catch (error) { return json({error:'request refused'}, error.status || 400); }
  }
  async provision(request, profile, bytes) {
    // Constant-time token comparison through SHA-256, no token in query/logs.
    const secret = this.env.PROVISIONING_TOKEN;
    require(typeof secret === 'string' && secret.length >= 32, 503);
    require(await hash(request.headers.get('Authorization') || '') === await hash('Bearer ' + secret), 401);
    const record = parse(bytes);
    require(record.profile === profile && id(record.generation) && id(record.home) &&
      /^04[0-9a-f]{128}$/.test(record.owner_key) && /^04[0-9a-f]{128}$/.test(record.home_key));
    require(Object.keys(record).sort().join() === ['profile','generation','home','owner_key','home_key'].sort().join());
    await this.storage.transaction(async tx => {
      require(!await tx.get('registry'), 409);
      await tx.put('registry', {...record, version:1, membership:1, cutoff:{revision:0, hash:'0'.repeat(64)},
        members:{[record.home]:record.home_key}, retired:[]});
    });
    return json({created:true}, 201);
  }
  async authenticate(request, profile, route, bytes) {
    require(request.method === 'POST' || (route === '/wake' && request.method === 'GET'), 405);
    const registry = await this.storage.get('registry');
    require(registry?.profile === profile, 409); // Never recreate lost authority metadata.
    const header = request.headers.get('X-Journal-Auth');
    require(header && header.length < 2048, 401);
    const {body, signature} = JSON.parse(header);
    require(body && Object.keys(body).sort().join() === ['device','generation','method','nonce','path','profile','sha256','time'].sort().join(), 401);
    require(id(body.device) && digest(body.nonce) && Number.isSafeInteger(body.time) && Math.abs(Date.now() - body.time) < 300000, 401);
    require(body.profile === profile && body.method === request.method && body.path === `/profiles/${profile}${route}` && body.sha256 === await hash(bytes), 401);
    let publicKey = registry.members[body.device];
    if (body.generation !== registry.generation) {
      require(route === '/authority' || route === '/authority/chain', 409);
      const retired = await this.storage.get(`retired:${body.generation}`);
      publicKey = retired?.members?.[body.device];
    }
    require(await verify(publicKey, body, signature), 401);
    await this.storage.transaction(async tx => {
      const nonce = `nonce:${body.device}:${body.nonce}`;
      require(!await tx.get(nonce), 409);
      const minute = Math.floor(Date.now() / 60000), key = `rate:${body.device}`;
      const rate = await tx.get(key) || {minute, requests:0, bytes:0};
      if (rate.minute !== minute) Object.assign(rate, {minute, requests:0, bytes:0});
      // Reserve separate per-device control capacity. A bulk sender cannot starve registry reads.
      const control = route.startsWith('/authority') || route.startsWith('/membership');
      const rateKey = control ? `control:${body.device}` : key;
      const current = control ? (await tx.get(rateKey) || {minute, requests:0, bytes:0}) : rate;
      if (current.minute !== minute) Object.assign(current, {minute, requests:0, bytes:0});
      require(current.requests < (control ? 30 : 180) && current.bytes + bytes.length <= 8 * 1024 * 1024, 429);
      current.requests++; current.bytes += bytes.length;
      await tx.put(rateKey, current);
      const bucket = control ? 'control' : route.startsWith('/snapshot') ? 'snapshot' : 'sync';
      const month = `month:${bucket}:${new Date().toISOString().slice(0, 7)}`;
      const used = await tx.get(month) || 0;
      require(used < monthly(this.env, bucket), 429);
      await tx.put(month, used + 1);
      await tx.put(nonce, Date.now() + 300000);
    });
    const due = Date.now() + 300000, alarm = await this.storage.getAlarm();
    if (!alarm || alarm > due) await this.storage.setAlarm(due);
    return {device:body.device, registry};
  }
  async fence(tx, auth) {
    const registry = await tx.get('registry');
    require(registry.generation === auth.registry.generation && registry.membership === auth.registry.membership && registry.members[auth.device], 409);
  }
  async send(auth, data) {
    require(Object.keys(data).sort().join() === ['id','recipient','wire'].sort().join());
    require(digest(data.id) && id(data.recipient) && auth.registry.members[data.recipient]);
    require(typeof data.wire === 'string' && data.wire.length <= 87500);
    const wire = Uint8Array.from(atob(data.wire), c => c.charCodeAt(0));
    require(wire.length <= ENVELOPE && await hash(wire) === data.id);
    const envelope = parse(wire), body = envelope.body;
    require(body?.profile === auth.registry.profile && body.generation === auth.registry.generation &&
      body.sender === auth.device && body.recipient === data.recipient && body.type === 'journal-envelope');
    // Outer DER envelope signature is verified on the recipient before decryption;
    // this request itself is authenticated with WebCrypto's IEEE P1363 signature.
    const key = `mail:${data.recipient}:${auth.device}:${data.id}`;
    await this.storage.transaction(async tx => {
      await this.fence(tx, auth);
      if (await tx.get(key)) return;
      const quotaKey = `quota:${data.recipient}:${auth.device}`;
      const quota = await tx.get(quotaKey) || {count:0, bytes:0};
      const total = await tx.get('mail-bytes') || 0;
      require(quota.count < 512 && quota.bytes + wire.length <= 8 * 1024 * 1024, 429);
      require(total + wire.length <= 128 * 1024 * 1024, 429);
      // The wire has its own key, so listing a mailbox reads only small entries.
      await tx.put(key, {id:data.id, sender:auth.device, size:wire.length, expires:Date.now() + 30 * DAY});
      await tx.put('wire:' + key.slice(5), data.wire);
      await tx.put(quotaKey, {count:quota.count + 1, bytes:quota.bytes + wire.length});
      await tx.put('mail-bytes', total + wire.length);
    });
    this.state.waitUntil(this.hint(data.recipient, auth.registry.generation));
    return json({stored:true});
  }
  wake(auth, request) {
    require(request.headers.get('Upgrade')?.toLowerCase() === 'websocket', 426);
    require(this.state.getWebSockets(auth.device).length < 2, 429);
    const pair = new WebSocketPair(), [client, server] = Object.values(pair);
    this.state.acceptWebSocket(server, [auth.device]);
    server.serializeAttachment({device:auth.device, generation:auth.registry.generation});
    return new Response(null, {status:101, webSocket:client});
  }
  webSocketMessage(socket) { socket.close(1008, 'Wake hints only'); }
  webSocketClose(socket, code) { socket.close(code, 'Closed'); }
  async pushToken(auth, data) {
    require(Object.keys(data).join() === 'token' && typeof data.token === 'string' && data.token.length <= 4096);
    await this.storage.transaction(async tx => {
      await this.fence(tx, auth);
      if (data.token) await tx.put(`push:${auth.device}`, data.token);
      else await tx.delete(`push:${auth.device}`);
    });
    return json({registered:true});
  }
  async hint(recipient, generation) {
    for (const socket of this.state.getWebSockets(recipient)) {
      try { if (socket.deserializeAttachment()?.generation === generation) socket.send('{"wake":true}'); }
      catch (_) { /* Delivery remains in the mailbox until durable acknowledgement. */ }
    }
    if (!this.env.FIREBASE_SERVICE_ACCOUNT) return;
    const allowed = await this.storage.transaction(async tx => {
      const last = await tx.get(`push-last:${recipient}`) || 0;
      if (Date.now() - last < 60000) return false;
      await tx.put(`push-last:${recipient}`, Date.now());
      return true;
    });
    if (!allowed) return;
    const token = await this.storage.get(`push:${recipient}`);
    if (!token) return;
    try {
      const account = JSON.parse(this.env.FIREBASE_SERVICE_ACCOUNT);
      require(/^[a-z0-9-]+$/.test(account.project_id));
      const b64 = data => btoa(typeof data === 'string' ? data : String.fromCharCode(...new Uint8Array(data))).replace(/=/g,'').replace(/\+/g,'-').replace(/\//g,'_');
      const now = Math.floor(Date.now() / 1000);
      const unsigned = b64(JSON.stringify({alg:'RS256',typ:'JWT'})) + '.' + b64(JSON.stringify({iss:account.client_email,
        scope:'https://www.googleapis.com/auth/firebase.messaging', aud:'https://oauth2.googleapis.com/token',iat:now,exp:now+3600}));
      const der = Uint8Array.from(atob(account.private_key.replace(/-----[^-]+-----|\s/g,'')), c=>c.charCodeAt(0));
      const key = await crypto.subtle.importKey('pkcs8',der,{name:'RSASSA-PKCS1-v1_5',hash:'SHA-256'},false,['sign']);
      const assertion = unsigned + '.' + b64(await crypto.subtle.sign('RSASSA-PKCS1-v1_5',key,encoder.encode(unsigned)));
      const oauth = await fetch('https://oauth2.googleapis.com/token', {method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},
        body:new URLSearchParams({grant_type:'urn:ietf:params:oauth:grant-type:jwt-bearer',assertion}),signal:AbortSignal.timeout(5000)});
      if (!oauth.ok) return;
      const credentials = await oauth.json();
      await fetch(`https://fcm.googleapis.com/v1/projects/${account.project_id}/messages:send`, {method:'POST',
        headers:{Authorization:'Bearer ' + credentials.access_token,'Content-Type':'application/json'},
        body:JSON.stringify({message:{token,data:{kind:'journal-wake'},android:{priority:'normal',ttl:'300s'}}}),signal:AbortSignal.timeout(5000)});
    } catch (_) { /* Push cannot acknowledge, confirm or discard an edit. */ }
  }
  async receive(auth) {
    const entries = await this.storage.list({prefix:`mail:${auth.device}:`, limit:64});
    const messages = []; let bytes = 0;
    for (const [key, value] of entries) {
      if (!auth.registry.members[value.sender]) continue;
      if (value.expires < Date.now()) continue;
      if (messages.length && bytes + value.size > ENVELOPE) break;
      const wire = await this.storage.get('wire:' + key.slice(5));
      if (typeof wire !== 'string') continue;
      messages.push({id:value.id, sender:value.sender, wire}); bytes += value.size;
      if (messages.length >= 20) break;
    }
    return json({messages});
  }
  async removeMail(tx, key, value) {
    const [, recipient, sender] = key.split(':');
    const qkey = `quota:${recipient}:${sender}`, quota = await tx.get(qkey);
    require(quota && quota.count > 0 && quota.bytes >= value.size, 409);
    await tx.put(qkey, {count:quota.count - 1, bytes:quota.bytes - value.size});
    const total = await tx.get('mail-bytes');
    require(Number.isSafeInteger(total) && total >= value.size, 409);
    await tx.put('mail-bytes', total - value.size);
    await tx.delete(key);
    await tx.delete('wire:' + key.slice(5));
  }
  async ack(auth, data) {
    require(Array.isArray(data.messages) && data.messages.length <= 20 && Object.keys(data).join() === 'messages');
    await this.storage.transaction(async tx => {
      await this.fence(tx, auth);
      for (const entry of data.messages) {
        require(id(entry.sender) && digest(entry.id));
        const key = `mail:${auth.device}:${entry.sender}:${entry.id}`, value = await tx.get(key);
        if (value) await this.removeMail(tx, key, value);
      }
    });
    return json({acknowledged:true});
  }
  async startSnapshot(auth, data) {
    require(auth.device === auth.registry.home, 403);
    require(digest(data.id) && id(data.recipient) && auth.registry.members[data.recipient]);
    require(Number.isSafeInteger(data.size) && data.size > 0 && data.size <= SNAPSHOT && digest(data.sha256));
    require(typeof data.manifest === 'string' && data.manifest.length < 32768 && await hash(encoder.encode(data.manifest)) === data.id);
    await this.storage.transaction(async tx => {
      await this.fence(tx, auth);
      const prior = await tx.get(`snapshot:${data.id}`);
      if (prior) { require(prior.recipient === data.recipient && prior.sha256 === data.sha256 && prior.size === data.size, 409); return; }
      const existing = await tx.list({prefix:'snapshot:'});
      require(existing.size < 4 && [...existing.values()].reduce((n,s) => n + s.size, 0) + data.size <= 2 * SNAPSHOT, 429);
      await tx.put(`snapshot:${data.id}`, {...data, sender:auth.device, complete:false, expires:Date.now() + 7 * DAY});
    });
    return json({chunk_size:CHUNK});
  }
  async findSnapshot(auth, data, upload = false) {
    require(digest(data.id));
    const snapshot = await this.storage.get(`snapshot:${data.id}`);
    require(snapshot && snapshot.expires > Date.now(), 404);
    require((upload ? snapshot.sender === auth.device && auth.registry.home === auth.device : snapshot.recipient === auth.device || snapshot.sender === auth.device), 403);
    return snapshot;
  }
  async putChunk(auth, data) {
    const snapshot = await this.findSnapshot(auth, data, true);
    require(!snapshot.complete && Number.isSafeInteger(data.index) && data.index >= 0 && data.index < Math.ceil(snapshot.size / CHUNK));
    require(typeof data.bytes === 'string' && data.bytes.length < 44000 && digest(data.sha256));
    const bytes = Uint8Array.from(atob(data.bytes), c => c.charCodeAt(0));
    require(bytes.length === Math.min(CHUNK, snapshot.size - data.index * CHUNK) && await hash(bytes) === data.sha256);
    const chunkKey = `chunk:${data.id}:${String(data.index).padStart(5,'0')}`;
    await this.storage.transaction(async tx => {
      await this.fence(tx, auth);
      const current = await tx.get(`snapshot:${data.id}`), prior = await tx.get(chunkKey);
      require(current && current.expires > Date.now() && !current.complete && (!prior || prior === data.sha256), 409);
      // Bytes and immutable digest commit together in the free-plan SQLite
      // Durable Object. Keep data separate so status/expiry never loads a
      // complete checkpoint into the Worker's 128 MiB memory allowance.
      if (prior) return;
      await tx.put(`chunk-data:${data.id}:${String(data.index).padStart(5,'0')}`, bytes.buffer);
      await tx.put(chunkKey, data.sha256);
    });
    return json({stored:true});
  }
  async snapshotStatus(auth, data) {
    const snapshot = await this.findSnapshot(auth, data);
    return json({size:snapshot.size, sha256:snapshot.sha256, complete:snapshot.complete, manifest:snapshot.manifest,
      chunks:[...(await this.storage.list({prefix:`chunk:${data.id}:`})).keys()].map(key => Number(key.split(':')[2]))});
  }
  async finishSnapshot(auth, data) {
    await this.findSnapshot(auth, data, true);
    await this.storage.transaction(async tx => {
      await this.fence(tx, auth);
      const snapshot = await tx.get(`snapshot:${data.id}`);
      require((await tx.list({prefix:`chunk:${data.id}:`})).size === Math.ceil(snapshot.size / CHUNK), 409);
      snapshot.complete = true;
      await tx.put(`snapshot:${data.id}`, snapshot);
    });
    return json({complete:true});
  }
  async getChunk(auth, data) {
    const snapshot = await this.findSnapshot(auth, data);
    require(snapshot.complete && Number.isSafeInteger(data.index) && data.index >= 0, 409);
    const sha256 = await this.storage.get(`chunk:${data.id}:${String(data.index).padStart(5,'0')}`);
    require(sha256, 404);
    const dataKey = `chunk-data:${data.id}:${String(data.index).padStart(5,'0')}`;
    const object = await this.storage.get(dataKey);
    require(object instanceof ArrayBuffer, 409);
    const bytes = new Uint8Array(object);
    require(await hash(bytes) === sha256, 409);
    return json({sha256, bytes:btoa(String.fromCharCode(...bytes))});
  }
  async membership(auth, data) {
    require(auth.device === auth.registry.home, 403);
    require(data.previous === auth.registry.membership && data.version === data.previous + 1 && data.generation === auth.registry.generation);
    require(Object.keys(data.members).length > 0 && Object.keys(data.members).length <= 16 && data.members[auth.registry.home] === auth.registry.home_key);
    for (const [device,key] of Object.entries(data.members)) require(id(device) && /^04[0-9a-f]{128}$/.test(key));
    await this.storage.transaction(async tx => {
      await this.fence(tx, auth);
      const registry = await tx.get('registry');
      require(registry.membership === data.previous && registry.generation === data.generation, 409);
      if (data.key_update !== undefined) {
        require(typeof data.key_update === 'string' && data.key_update.length <= ENVELOPE);
        const update = parse(encoder.encode(data.key_update));
        require(data.key_version === (registry.key_version ?? 1) + 1 && update.body?.version === data.key_version &&
          update.body.type === 'journal-membership' && update.body.profile === registry.profile && update.body.generation === registry.generation);
        await tx.put(`membership-wire:${data.key_version}`,data.key_update);
        registry.key_version = data.key_version;
      }
      registry.membership = data.version; registry.members = data.members;
      await tx.put('registry', registry);
    });
    for (const socket of this.state.getWebSockets()) if (!data.members[socket.deserializeAttachment()?.device]) socket.close(1008,'Membership changed');
    return json({updated:true});
  }
  async membershipUpdate(auth,data) {
    require(Object.keys(data).join() === 'version' && Number.isSafeInteger(data.version) && data.version >= 0);
    require(data.version < (auth.registry.key_version ?? 1),409);
    const update = await this.storage.get(`membership-wire:${data.version+1}`);
    require(update,409);
    return json({update, latest:auth.registry.key_version});
  }
  async authorityChain(auth,data) {
    require(Object.keys(data).join() === 'after' && Number.isSafeInteger(data.after) && data.after >= 1 && data.after <= auth.registry.version);
    const certificates = [];
    for (let version=data.after+1; version<=Math.min(data.after+8,auth.registry.version); version++) {
      const certificate = await this.storage.get(`authority-version:${version}`) ||
        (version === auth.registry.version ? auth.registry.certificate : null);
      require(certificate,409);
      certificates.push(certificate);
    }
    return json({certificates,latest:auth.registry.version});
  }
  async transition(auth, data) {
    const {body, signature} = data;
    require(body && Object.keys(body).sort().join() === ['cutoff','generation','home','home_key','mode','nonce','owner_key','previous','profile','version'].sort().join());
    require(body.profile === auth.registry.profile && body.previous === auth.registry.generation && body.generation !== body.previous && id(body.generation) && id(body.home));
    require(body.version === auth.registry.version + 1 && ['move','recover','rotate-owner'].includes(body.mode) && digest(body.nonce));
    require(/^04[0-9a-f]{128}$/.test(body.home_key) && /^04[0-9a-f]{128}$/.test(body.owner_key));
    require(Number.isSafeInteger(body.cutoff?.revision) && body.cutoff.revision >= 0 && digest(body.cutoff.hash));
    require(await verify(auth.registry.owner_key, body, signature), 403);
    await this.storage.transaction(async tx => {
      await this.fence(tx, auth);
      const registry = await tx.get('registry');
      require(registry.generation === body.previous && registry.version + 1 === body.version, 409);
      require(!await tx.get(`transition:${body.nonce}`), 409);
      // Durable retirement/certificates are never expired with message queues.
      await tx.put(`retired:${registry.generation}`, {generation:registry.generation, home:registry.home, members:registry.members, certificate:data});
      await tx.put(`transition:${body.nonce}`, data);
      await tx.put(`authority-version:${body.version}`, data);
      await tx.put('registry', {...registry, generation:body.generation, home:body.home, home_key:body.home_key,
        owner_key:body.owner_key, version:body.version, cutoff:body.cutoff, membership:registry.membership + 1,
        members:{[body.home]:body.home_key}, key_version:0, certificate:data, retired:[]});
    });
    for (const socket of this.state.getWebSockets()) socket.close(1008,'Authority changed');
    return json({activated:true});
  }
  async alarm() {
    // Expiry removes only opaque delivery state, never authority or retirement.
    const now = Date.now();
    for (const [key,value] of await this.storage.list({prefix:'nonce:'})) if (value < now) await this.storage.delete(key);
    for (const [key,value] of await this.storage.list({prefix:'mail:'})) if (value.expires < now) {
      await this.storage.transaction(async tx => { const current = await tx.get(key); if (current && current.expires < now) await this.removeMail(tx,key,current); });
    }
    for (const [key,value] of await this.storage.list({prefix:'snapshot:'})) if (value.expires < now) {
      for (const chunkKey of (await this.storage.list({prefix:`chunk:${value.id}:`})).keys()) {
        const dataKey = chunkKey.replace('chunk:', 'chunk-data:');
        await this.storage.transaction(async tx => {
          await tx.delete(dataKey);
          await tx.delete(chunkKey);
        });
      }
      await this.storage.delete(key);
    }
    const deadlines = [
      ...[...(await this.storage.list({prefix:'nonce:'})).values()],
      ...[...(await this.storage.list({prefix:'mail:'})).values()].map(value => value.expires),
      ...[...(await this.storage.list({prefix:'snapshot:'})).values()].map(value => value.expires),
    ];
    if (deadlines.length) await this.storage.setAlarm(Math.max(now + 1000, Math.min(...deadlines)));
    else await this.storage.deleteAlarm();
  }
}
