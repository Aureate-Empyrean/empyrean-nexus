import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFile} from 'node:fs/promises';
import {matchRoute} from '../frontend/router.js';
const source = await readFile(new URL('../frontend/navigation-protocol.js',import.meta.url),'utf8');

function sandbox() {
  const listeners = new Map(), sent = [];
  const parent = {postMessage: (message,origin) => sent.push({message,origin})};
  const window = {parent,addEventListener: (name,callback) => listeners.set(name,callback)};
  const context = vm.createContext({window,parent,document:{referrer:'http://localhost/app/modules/pilot'},
    location:new URL('http://localhost/modules/pilot/'),crypto,URL,URLSearchParams,TextEncoder,
    setTimeout,clearTimeout,setInterval,clearInterval});
  vm.runInContext(source,context);
  return {api:context.EmpyreanNavigation,context,listeners,sent,parent};
}
test('real router keeps old URL shapes and rejects ambiguous new envelopes', () => {
  assert.deepEqual(matchRoute('/app/modules/pilot','?path=/w/a/r/b'),{name:'module',id:'pilot',modulePath:'/w/a/r/b'});
  assert.equal(matchRoute('/app/modules/pilot','?nav=1&route=%2Fw%2Fa%2Ftasks%3Ftask%3Db').navigationRoute,'/w/a/tasks?task=b');
  for (const search of ['?nav=2&route=/tasks','?nav=1','?nav=1&route=/a&route=/b','?nav=1&route=//evil','?nav=1&route=/%2e%2e/a'])
    assert.equal(matchRoute('/app/modules/pilot',search).name,'not-found',search);
});
test('shared SDK source is identical to the Mnemosyne vendored bundle', async () => {
  const copy = await readFile(new URL('../../mnemosyne/frontend/vendor/nexus-navigation.js',import.meta.url),'utf8');
  assert.equal(copy,source);
});
test('host validates source/session/revision, preserves URL/state and avoids duplicate entries', async t => {
  const {api,context} = sandbox(), sent = [], entries = [], data = new Map();
  context.location = new URL('http://localhost/app/modules/pilot?path=/existing&keep=yes');
  let current = {id:'pilot',modulePath:'/existing'}, active = true;
  context.history = {state:{foreign:42},pushState(state,title,path) {entries.push(path);this.state=state;context.location=new URL(path,context.location);},
    replaceState(state,title,path) {this.state=state;context.location=new URL(path,context.location);}};
  const child = {postMessage: message => sent.push(message)}, frame = {isConnected:true,contentWindow:child};
  const storage = {getItem:key => data.get(key), setItem:(key,value)=>data.set(key,value)};
  const host = api.createHost({active:()=>active,current:()=>current,commit:route=>{current={...current,navigationRoute:route};},report:()=>{},owner:()=> 'owner',storage});
  t.after(()=>host.reset()); host.bind(frame,'pilot');
  const send = (message,source=child) => host.receive({source,data:{channel:api.channel,...message}});
  send({type:'hello',document:'doc',version:1},{}); assert.equal(sent.length,0);
  send({type:'hello',document:'doc',version:1});
  send({type:'hello',document:'doc',version:1,challenge:sent.at(-1).challenge});
  let restore = sent.at(-1);
  const commit = {type:'commit',session:restore.session,baseRevision:restore.revision,mode:'push',route:'/notes?tab=one#part'};
  send({...commit,session:'retired'}); assert.equal(entries.length,0);
  send(commit); assert.equal(entries.length,1);
  assert.equal(context.history.state.foreign,42);
  assert.equal(context.location.searchParams.get('path'),'/existing');
  assert.equal(context.location.searchParams.get('keep'),'yes');
  assert.equal(context.location.searchParams.get('route'),'/notes?tab=one#part');
  restore = sent.at(-1);
  send({...commit,baseRevision:restore.revision}); assert.equal(entries.length,1);
  send(commit); assert.equal(entries.length,1); assert.equal(sent.at(-1).cause,'resync');
  restore = sent.at(-1);
  send({...commit,baseRevision:restore.revision,route:'//evil'}); assert.equal(entries.length,1);
  const leaving = host.prepareLeave();
  const prepare = sent.at(-1);
  send({...commit,baseRevision:prepare.revision,route:'/late-click'});
  assert.equal(sent.at(-1).code,'leaving'); assert.equal(entries.length,1);
  send({type:'prepared',session:prepare.session,id:prepare.id});
  await leaving;
  host.restore('traversal');
  active=false; send({...commit,baseRevision:restore.revision,route:'/tasks'}); assert.equal(entries.length,1);
});
test('draft checkpoints stay scoped to the active frame and fail explicitly on storage quota', t => {
  const {api} = sandbox(), sent = [], data = new Map();
  const source = {postMessage: message => sent.push(message)}, frame = {isConnected:true,contentWindow:source};
  let fail = false;
  const host = api.createHost({active:()=>true,current:()=>({modulePath:'/'}),commit:()=>{},report:()=>{},owner:()=> 'alice',
    storage:{getItem:key=>data.get(key),setItem:(key,value)=>{if(fail)throw Error('quota');data.set(key,value);}}});
  t.after(()=>host.reset());host.bind(frame,'pilot');
  const receive = (message, sender=source) => host.receive({source:sender,data:{channel:api.channel,...message}});
  receive({type:'hello',version:1,document:'doc'});
  receive({type:'hello',version:1,document:'doc',challenge:sent.at(-1).challenge});
  const session=sent.at(-1).session;
  receive({type:'checkpoint',id:1,session,value:{text:'draft'}},{}); assert.equal(data.size,0);
  receive({type:'checkpoint',id:1,session,value:{text:'draft'}});
  assert.equal(data.get('nexus.navigation.drafts.v1:alice:pilot'),'{"text":"draft"}');
  assert.equal(sent.at(-1).type,'checkpointed');
  fail=true; receive({type:'checkpoint',id:2,session,value:{text:'new draft'}});
  assert.ok(sent.at(-1).error); assert.equal(data.values().next().value,'{"text":"draft"}');
});
test('old host negotiation remains silent; supported client serializes restoration and rejects stale intents', async () => {
  const {api,sent,listeners,parent} = sandbox();
  let applied = [];
  const client = api.createClient({apply: async route=>{applied.push(route);}});
  assert.equal(await client.start({}),false); assert.equal(sent.length,0);
  const starting = client.start({navigation:{versions:[1]}});
  const hello = sent.at(-1).message;
  const restore = (route,revision,cause='traversal',source=parent) => listeners.get('message')({source,origin:'http://localhost',
    data:{channel:api.channel,type:'restore',document:hello.document,session:'session',revision,route,cause}});
  restore('/forged',1,'initial',{}); assert.equal(applied.length,0);
  restore('/notes',1,'initial'); await starting; assert.deepEqual(applied,['/notes']);
  const pending = client.navigate('/tasks');
  restore('/other',2); await assert.rejects(pending,/superseded/);
  await new Promise(resolve=>setTimeout(resolve,0));
  restore('/obsolete',1); assert.equal(client.route,'/other');
  const checkpoint = client.checkpoint({version:1,entries:[]});
  const outgoing = sent.at(-1).message;
  listeners.get('message')({source:parent,origin:'http://localhost',data:{channel:api.channel,type:'checkpointed',session:'session',id:outgoing.id}});
  await checkpoint;
  listeners.get('message')({source:parent,origin:'http://localhost',data:{channel:api.channel,type:'prepare-leave',session:'session',revision:3,id:'leave-id'}});
  await new Promise(resolve=>setTimeout(resolve,0));
  assert.equal(sent.at(-1).message.type,'prepared');
  assert.equal(sent.at(-1).message.id,'leave-id');
});
