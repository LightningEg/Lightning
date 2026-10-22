import {test, before, after} from 'node:test';
import assert from 'node:assert/strict';
import {createHash, randomBytes, randomUUID, webcrypto} from 'node:crypto';
import {Miniflare} from 'miniflare';
import {canonical, ProfileMailbox} from './worker.mjs';

const checksum = bytes => createHash('sha256').update(bytes).digest('hex');
const token = 'test-only-provisioning-token-' + randomBytes(32).toString('hex');
let mf;
before(() => {
  mf = new Miniflare({modules:true, scriptPath:new URL('./worker.mjs', import.meta.url).pathname,
    compatibilityDate:'2026-07-30', durableObjects:{PROFILES:{className:'ProfileMailbox', useSQLite:true}},
    bindings:{PROVISIONING_TOKEN:token, DEPLOYMENT_POLICY:'free-only'}});
});
after(async () => { await mf.dispose(); });
async function identity() {
  const pair = await webcrypto.subtle.generateKey({name:'ECDSA', namedCurve:'P-256'}, true, ['sign','verify']);
  return {id:randomUUID(), key:pair.privateKey, public:Buffer.from(await webcrypto.subtle.exportKey('raw', pair.publicKey)).toString('hex')};
}
async function sign(key, data) {
  return Buffer.from(await webcrypto.subtle.sign({name:'ECDSA', hash:'SHA-256'}, key, Buffer.from(canonical(data)))).toString('hex');
}
async function profile() {
  const home = await identity(), pc = await identity(), owner = await identity();
  const config = {profile:randomUUID(), generation:randomUUID(), home:home.id, home_key:home.public, owner_key:owner.public};
  let response = await mf.dispatchFetch(`https://journal.test/profiles/${config.profile}/provision`, {method:'POST',
    headers:{Authorization:'Bearer ' + token}, body:canonical(config)});
  assert.equal(response.status, 201);
  const lab = {home,pc,owner,config};
  response = await request(lab, home, '/membership', {previous:1,version:2,generation:config.generation,
    members:{[home.id]:home.public,[pc.id]:pc.public}});
  assert.equal(response.status, 200);
  return lab;
}
async function makeRequest(lab, who, route, data = {}, method = 'POST') {
  const bytes = method === 'GET' ? '' : canonical(data), path = `/profiles/${lab.config.profile}${route}`;
  const body = {device:who.id, generation:lab.config.generation, method, path, profile:lab.config.profile,
    sha256:checksum(bytes), time:Date.now(), nonce:randomBytes(32).toString('hex')};
  return {url:'https://journal.test' + path, init:{method, ...(method === 'GET' ? {} : {body:bytes}),
    headers:{'X-Journal-Auth':JSON.stringify({body,signature:await sign(who.key, body)})}}};
}
async function request(lab,who,route,data={}) {
  const prepared = await makeRequest(lab,who,route,data);
  return mf.dispatchFetch(prepared.url,prepared.init);
}
function message(lab, sender, recipient) {
  const wire=canonical({body:{type:'journal-envelope',profile:lab.config.profile,generation:lab.config.generation,
    sender:sender.id,recipient:recipient.id,ciphertext:randomBytes(40).toString('hex')},signature:'00'.repeat(64)});
  return {id:checksum(wire),recipient:recipient.id,wire:Buffer.from(wire).toString('base64')};
}
test('authenticated provision, body binding, replay and cross-profile admission', async () => {
  const lab=await profile();
  const prepared=await makeRequest(lab,lab.pc,'/receive');
  assert.equal((await mf.dispatchFetch(prepared.url,prepared.init)).status,200);
  assert.equal((await mf.dispatchFetch(prepared.url,prepared.init)).status,409);
  const changed=await makeRequest(lab,lab.pc,'/receive');
  assert.equal((await mf.dispatchFetch(changed.url,{...changed.init,body:'{"tampered":true}'})).status,401);
  assert.equal((await request(lab,await identity(),'/receive')).status,401);
  assert.equal((await mf.dispatchFetch(`https://journal.test/profiles/${lab.config.profile}/provision`,
    {method:'POST',headers:{Authorization:'Bearer ' + token},body:canonical(lab.config)})).status,409);
});
test('download retains opaque delivery until recipient ack; duplicate send has one entry', async () => {
  const lab=await profile(), item=message(lab,lab.pc,lab.home);
  assert.equal((await request(lab,lab.pc,'/send',item)).status,200);
  assert.equal((await request(lab,lab.pc,'/send',item)).status,200);
  const first=await (await request(lab,lab.home,'/receive')).json();
  assert.equal(first.messages.length,1);
  assert.equal((await (await request(lab,lab.home,'/receive')).json()).messages.length,1);
  assert.equal((await (await request(lab,lab.pc,'/receive')).json()).messages.length,0);
  assert.equal((await request(lab,lab.home,'/ack',{messages:[{id:item.id,sender:lab.pc.id}]})).status,200);
  assert.equal((await (await request(lab,lab.home,'/receive')).json()).messages.length,0);
});
test('snapshot chunks resume, remain immutable and require completion and recipient membership', async () => {
  const lab=await profile(), bytes=randomBytes(32768 + 10), manifest=canonical({opaque:'signed manifest from device'});
  const snapshot={id:checksum(manifest),recipient:lab.pc.id,size:bytes.length,sha256:checksum(bytes),manifest};
  assert.equal((await request(lab,lab.home,'/snapshot/start',snapshot)).status,200);
  assert.equal((await request(lab,lab.home,'/snapshot/finish',{id:snapshot.id})).status,409);
  for(let index=0;index<2;index++) {
    const part=bytes.subarray(index*32768,(index+1)*32768);
    const chunk={id:snapshot.id,index,bytes:part.toString('base64'),sha256:checksum(part)};
    assert.equal((await request(lab,lab.home,'/snapshot/put',chunk)).status,200);
    assert.equal((await request(lab,lab.home,'/snapshot/put',chunk)).status,200);
  }
  assert.deepEqual((await (await request(lab,lab.home,'/snapshot/status',{id:snapshot.id})).json()).chunks,[0,1]);
  assert.equal((await request(lab,lab.home,'/snapshot/finish',{id:snapshot.id})).status,200);
  const first=await (await request(lab,lab.pc,'/snapshot/get',{id:snapshot.id,index:0})).json();
  assert.deepEqual(Buffer.from(first.bytes,'base64'),bytes.subarray(0,32768));
  assert.equal((await request(lab,lab.pc,'/snapshot/put',{id:snapshot.id,index:0,bytes:first.bytes,sha256:first.sha256})).status,403);
});
test('atomic owner-signed generation transition admits exactly one recovery', async () => {
  const lab=await profile();
  const make=async () => {
    const body={profile:lab.config.profile,previous:lab.config.generation,generation:randomUUID(),home:lab.pc.id,
      home_key:lab.pc.public,owner_key:lab.owner.public,version:2,mode:'recover',nonce:randomBytes(32).toString('hex'),cutoff:{revision:0,hash:'0'.repeat(64)}};
    return {body,signature:await sign(lab.owner.key,body)};
  };
  const wrong=await make(); wrong.signature=await sign(lab.pc.key,wrong.body);
  assert.equal((await request(lab,lab.pc,'/authority/transition',wrong)).status,403);
  const [left,right]=await Promise.all([make(),make()]);
  const results=await Promise.all([request(lab,lab.pc,'/authority/transition',left),request(lab,lab.pc,'/authority/transition',right)]);
  assert.deepEqual(results.map(r=>r.status).sort(),[200,409]);
  assert.equal((await request(lab,lab.home,'/send',message(lab,lab.home,lab.pc))).status,409);
  const current = await (await request(lab,lab.home,'/authority')).json();
  assert.equal(current.version,2);
});
test('hibernating foreground socket carries only a wake hint; delivery still requires ack', async () => {
  const lab=await profile(), prepared=await makeRequest(lab,lab.home,'/wake',{},'GET');
  prepared.init.headers.Upgrade='websocket';
  const response=await mf.dispatchFetch(prepared.url,prepared.init);
  assert.equal(response.status,101);
  const socket=response.webSocket;
  socket.accept();
  const hinted=new Promise((resolve,reject) => {
    const timeout=setTimeout(()=>reject(new Error('No wake hint')),2000);
    socket.addEventListener('message',event=>{clearTimeout(timeout);resolve(event.data);},{once:true});
  });
  await request(lab,lab.pc,'/send',message(lab,lab.pc,lab.home));
  assert.equal(await hinted,'{"wake":true}');
  assert.equal((await (await request(lab,lab.home,'/receive')).json()).messages.length,1);
  socket.close(1000,'Test finished');
});
test('revoking a device closes its authenticated queue admission', async () => {
  const lab=await profile();
  assert.equal((await request(lab,lab.home,'/membership',{previous:2,version:3,generation:lab.config.generation,
    members:{[lab.home.id]:lab.home.public}})).status,200);
  assert.equal((await request(lab,lab.pc,'/send',message(lab,lab.pc,lab.home))).status,401);
  assert.equal((await request(lab,lab.home,'/authority')).status,200);
});
test('snapshot reservation quota stops new uploads while authority remains readable', async () => {
  const lab=await profile();
  for (let index=0;index<2;index++) {
    const manifest=canonical({opaque:'dummy reservation ' + index});
    const snapshot={id:checksum(manifest),recipient:lab.pc.id,size:200*1024*1024,sha256:'a'.repeat(64),manifest};
    assert.equal((await request(lab,lab.home,'/snapshot/start',snapshot)).status,200);
  }
  const manifest=canonical({opaque:'over quota'});
  assert.equal((await request(lab,lab.home,'/snapshot/start',{
    id:checksum(manifest),recipient:lab.pc.id,size:1,sha256:'a'.repeat(64),manifest})).status,429);
  assert.equal((await request(lab,lab.home,'/authority')).status,200);
});
test('expired snapshot bytes and mail are cleaned while authority history survives', async () => {
  const id='a'.repeat(64), past=Date.now()-1000;
  const values=new Map([
    ['registry',{profile:randomUUID()}], ['retired:old-generation',{certificate:'retained'}],
    [`snapshot:${id}`,{id,expires:past}], [`chunk:${id}:00000`,'b'.repeat(64)],
    [`chunk-data:${id}:00000`,new ArrayBuffer(32)], ['nonce:old',past],
    ['mail:recipient:sender:message',{expires:past,size:32}],
    ['quota:recipient:sender',{count:1,bytes:32}], ['mail-bytes',32],
  ]);
  let nextAlarm;
  const storage={get:async key=>values.get(key),put:async(key,value)=>values.set(key,value),delete:async key=>values.delete(key),
    list:async({prefix})=>new Map([...values].filter(([key])=>key.startsWith(prefix))),
    transaction:async callback=>callback(storage),setAlarm:async value=>{nextAlarm=value;},deleteAlarm:async()=>{nextAlarm=null;}};
  await new ProfileMailbox({storage},{}).alarm();
  assert.equal(values.has(`snapshot:${id}`),false);
  assert.equal(values.has(`chunk-data:${id}:00000`),false);
  assert.equal(values.has(`chunk:${id}:00000`),false);
  assert.equal(values.has('nonce:old'),false);
  assert.equal(values.get('mail-bytes'),0);
  assert.deepEqual(values.get('quota:recipient:sender'),{count:0,bytes:0});
  assert.equal(values.has('retired:old-generation'),true);
  assert.equal(values.has('registry'),true);
  assert.equal(nextAlarm,null);
});

test('existing members fetch key updates and revoked members lose access', async () => {
  const lab=await profile();
  const update=canonical({body:{type:'journal-membership',profile:lab.config.profile,generation:lab.config.generation,version:2},signature:'opaque-home-signature'});
  let response=await request(lab,lab.home,'/membership',{previous:2,version:3,generation:lab.config.generation,
    members:{[lab.home.id]:lab.home.public,[lab.pc.id]:lab.pc.public},key_version:2,key_update:update});
  assert.equal(response.status,200);
  response=await request(lab,lab.pc,'/membership/update',{version:1});
  assert.equal(response.status,200);
  assert.equal((await response.json()).update,update);
  assert.equal((await request(lab,lab.pc,'/membership/update',{version:2})).status,409);
  assert.equal((await request(lab,lab.home,'/membership',{previous:3,version:4,generation:lab.config.generation,
    members:{[lab.home.id]:lab.home.public}})).status,200);
  assert.equal((await request(lab,lab.pc,'/membership/update',{version:1})).status,401);
});

test('offline devices can fetch consecutive retirement certificates across owner-key changes', async () => {
  const lab=await profile(), replacement=await identity();
  const first={profile:lab.config.profile,previous:lab.config.generation,generation:randomUUID(),home:lab.pc.id,
    home_key:lab.pc.public,owner_key:replacement.public,version:2,mode:'recover',nonce:randomBytes(32).toString('hex'),cutoff:{revision:0,hash:'0'.repeat(64)}};
  const firstCertificate={body:first,signature:await sign(lab.owner.key,first)};
  assert.equal((await request(lab,lab.pc,'/authority/transition',firstCertificate)).status,200);
  const nextLab={...lab,config:{...lab.config,generation:first.generation}};
  const second={...first,previous:first.generation,generation:randomUUID(),version:3,nonce:randomBytes(32).toString('hex')};
  const secondCertificate={body:second,signature:await sign(replacement.key,second)};
  assert.equal((await request(nextLab,lab.pc,'/authority/transition',secondCertificate)).status,200);
  const response=await request(lab,lab.home,'/authority/chain',{after:1});
  assert.equal(response.status,200);
  assert.deepEqual(await response.json(),{certificates:[firstCertificate,secondCertificate],latest:3});
  assert.equal((await request(lab,lab.home,'/send',message(lab,lab.home,lab.pc))).status,409);
});

test('a successor publishes a fresh initial transport wrap for its new generation', async () => {
  const lab=await profile();
  const body={profile:lab.config.profile,previous:lab.config.generation,generation:randomUUID(),home:lab.pc.id,
    home_key:lab.pc.public,owner_key:lab.owner.public,version:2,mode:'recover',nonce:randomBytes(32).toString('hex'),cutoff:{revision:0,hash:'0'.repeat(64)}};
  assert.equal((await request(lab,lab.pc,'/authority/transition',{body,signature:await sign(lab.owner.key,body)})).status,200);
  const current={...lab,config:{...lab.config,generation:body.generation}};
  const registry=await (await request(current,lab.pc,'/authority')).json();
  assert.equal(registry.key_version,0);
  const key_update=canonical({body:{type:'journal-membership',profile:body.profile,generation:body.generation,previous:0,version:1},signature:'opaque-device-signature'});
  assert.equal((await request(current,lab.pc,'/membership',{previous:registry.membership,version:registry.membership+1,generation:body.generation,
    members:{[lab.pc.id]:lab.pc.public,[lab.home.id]:lab.home.public},key_version:1,key_update})).status,200);
  const response=await request(current,lab.home,'/membership/update',{version:0});
  assert.equal(response.status,200);
  assert.equal((await response.json()).update,key_update);
});
test('each profile has a monthly sync allowance; registry calls keep their own', async () => {
  const shared = mf;
  mf = new Miniflare({modules:true, scriptPath:new URL('./worker.mjs', import.meta.url).pathname,
    compatibilityDate:'2026-07-30', durableObjects:{PROFILES:{className:'ProfileMailbox', useSQLite:true}},
    bindings:{PROVISIONING_TOKEN:token, DEPLOYMENT_POLICY:'free-only', MONTHLY_REQUESTS:'3'}});
  try {
    const lab = await profile();
    for (let i = 0; i < 3; i++) assert.equal((await request(lab,lab.pc,'/receive')).status,200);
    assert.equal((await request(lab,lab.pc,'/receive')).status,429);
    assert.equal((await request(lab,lab.home,'/receive')).status,429); // Per profile, not per device.
    assert.equal((await request(lab,lab.pc,'/authority')).status,200);
    const other = await profile();
    assert.equal((await request(other,other.pc,'/receive')).status,200);
  } finally { await mf.dispose(); mf = shared; }
});
