import { test } from 'node:test';
import assert from 'node:assert/strict';
import { generateKeyPairSync, sign } from 'node:crypto';
import { act, handle } from '../src/index.mjs';
const APP_ID = '123456789012345678';
const GUILD_ID = '223456789012345678';
const USER_ID = '323456789012345678';
const { publicKey, privateKey } = generateKeyPairSync('ed25519');
const PUBLIC_KEY = publicKey.export({format:'der',type:'spki'}).subarray(-32).toString('hex');
const env = { PUBLIC_KEY, APP_ID, GUILD_ID, DISCORD_TOKEN: 'never-real', OPERATOR_IDS: USER_ID };
const interaction = (name, opts=[], who=USER_ID) => ({type:2, application_id:APP_ID, guild_id:GUILD_ID, token:'fake',member:{user:{id:who}},data:{options:[{name,options:opts}]}});
const makeRequest = (data, signatureOverride) => {
  const body=JSON.stringify(data), timestamp=String(Math.trunc(Date.now()/1000));
  const signature=sign(null,Buffer.from(timestamp+body),privateKey).toString('hex');
  return new Request('https://worker.example/interactions',{method:'POST',headers:{'X-Signature-Ed25519':signatureOverride??signature,'X-Signature-Timestamp':timestamp},body});
};
test('rejects unsigned and invalid requests',async()=>{
  assert.equal((await handle(makeRequest({type:1}, '11'.repeat(64)),env,{})).status,401);
  assert.equal((await handle(new Request('https://worker.example/interactions'),env,{})).status,404);
});
test('handshake is signed and accepted',async()=>{
  assert.equal((await (await handle(makeRequest({type:1}),env,{})).json()).type,1);
});
test('wrong guild is blocked without async action',async()=>{
  let called=false;
  const item=interaction('channel');item.guild_id='987654321012345678';
  const out=await handle(makeRequest(item),env,{waitUntil(){called=true;}});
  assert.equal((await out.json()).type,4);
  assert.equal(called,false);
});
test('operator-only commands reject non-operator before any API work',async()=>{
  assert.match(await act(interaction('channel',[{name:'name',value:'new-room'}],'999999999999999999'),env),/designated Lightning operator/);
});
test('valid ping defers action to worker',async()=>{
  const previousFetch=globalThis.fetch;
  globalThis.fetch=async()=>new Response('{}',{status:200});
  try {
    let task;const out=await handle(makeRequest(interaction('ping')),env,{waitUntil(p){task=p;}});
    assert.equal((await out.json()).type,5);
    assert.ok(task);
    await task;
  } finally { globalThis.fetch=previousFetch; }
});
test('bad channel names are rejected locally',async()=>{
  assert.match(await act(interaction('channel',[{name:'name',value:'Bad Name'}]),env),/lowercase/);
});
