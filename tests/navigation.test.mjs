import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFile} from 'node:fs/promises';
import {existsSync} from 'node:fs';
import {matchRoute} from '../frontend/router.js';
const source = await readFile(new URL('../frontend/navigation-protocol.js',import.meta.url),'utf8');

function sandbox(timers = {setTimeout,clearTimeout,setInterval,clearInterval}) {
  const listeners = new Map(), sent = [];
  const parent = {postMessage: (message,origin) => sent.push({message,origin})};
  const window = {parent,addEventListener: (name,callback) => listeners.set(name,callback)};
  const context = vm.createContext({window,parent,document:{referrer:'http://localhost/app/modules/pilot'},
    location:new URL('http://localhost/modules/pilot/'),crypto,URL,URLSearchParams,TextEncoder,
    ...timers});
  vm.runInContext(source,context);
  return {api:context.EmpyreanNavigation,context,listeners,sent,parent};
}
/** Hello intervals advance only when a test says so, so a timeout is deterministic. */
function manualTimers() {
  const intervals = new Set();
  return {intervals, tick() { for (const callback of [...intervals]) callback(); },
    timers:{setTimeout,clearTimeout,setInterval:callback => { intervals.add(callback); return callback; }, clearInterval:handle => intervals.delete(handle)}};
}
function makeHost(api, context, {owner = 'owner', current = {id:'pilot',modulePath:'/'}, report = () => {}} = {}) {
  const sent = [], data = new Map();
  context.history = {state:null,length:1,pushState(state,title,path) {this.length++;this.state=state;context.location=new URL(path,context.location);},
    replaceState(state,title,path) {this.state=state;context.location=new URL(path,context.location);}};
  context.location = new URL('http://localhost/app/modules/pilot');
  const child = {postMessage: message => sent.push(message)}, frame = {isConnected:true,contentWindow:child};
  const storage = {getItem:key => data.get(key) ?? null, setItem:(key,value)=>data.set(key,value), removeItem:key=>data.delete(key),
    key:i=>[...data.keys()][i], get length() {return data.size;}};
  const state = {current};
  const host = api.createHost({active:()=>true,current:()=>state.current,commit:route=>{state.current={...state.current,navigationRoute:route};},report,owner:()=>owner,storage});
  host.bind(frame,'pilot');
  const send = message => host.receive({source:child,data:{channel:api.channel,...message}});
  send({type:'hello',document:'doc',version:1});
  send({type:'hello',document:'doc',version:1,challenge:sent.at(-1).challenge});
  return {host,send,sent,data,state,session:sent.at(-1).session};
}
test('real router keeps old URL shapes and rejects ambiguous new envelopes', () => {
  assert.deepEqual(matchRoute('/app/modules/pilot','?path=/w/a/r/b'),{name:'module',id:'pilot',modulePath:'/w/a/r/b'});
  assert.equal(matchRoute('/app/modules/pilot','?nav=1&route=%2Fw%2Fa%2Ftasks%3Ftask%3Db').navigationRoute,'/w/a/tasks?task=b');
  for (const search of ['?nav=2&route=/tasks','?nav=1','?nav=1&route=/a&route=/b','?nav=1&route=//evil','?nav=1&route=/%2e%2e/a'])
    assert.equal(matchRoute('/app/modules/pilot',search).name,'not-found',search);
});
const vendored = ['mnemosyne','meridian','lyra','chronos','atlas','argus'].map(module => [module,new URL(`../../${module}/frontend/vendor/nexus-navigation.js`,import.meta.url)]);
// CI checks out Nexus alone; in the workspace this and scripts/sync-navigation.mjs --check cover every module.
test('shared SDK source is identical to every vendored bundle',{skip:vendored.every(([,url]) => existsSync(url)) ? false : 'sibling module checkouts are not present'},async () => {
  for (const [module,url] of vendored) assert.equal(await readFile(url,'utf8'),source,module);
});
test('a handshake that times out leaves the client failed, not falsely enabled', async () => {
  const clock = manualTimers(), {api,listeners,sent,parent} = sandbox(clock.timers);
  let applied = 0;
  const client = api.createClient({apply: async () => {applied++;}});
  assert.equal(client.status,'idle'); assert.equal(client.enabled,false);
  const starting = client.start({navigation:{versions:[1]}});
  assert.equal(client.status,'handshaking'); assert.equal(client.enabled,false,'no session has been granted yet');
  assert.equal(client.start({navigation:{versions:[1]}}),starting,'a concurrent start joins the same attempt');
  for (let i = 0; i < 5; i++) clock.tick();
  await assert.rejects(starting,/timed out/);
  assert.equal(client.status,'failed'); assert.equal(client.enabled,false);
  assert.equal(clock.intervals.size,0,'the hello timer stops');
  await assert.rejects(client.navigate('/people'),/not ready/);
  await client.checkpoint({version:1}); // resolves without storing, like an unsupported host
  const hello = sent[0].message;
  listeners.get('message')({source:parent,origin:'http://localhost',data:{channel:api.channel,type:'restore',document:hello.document,session:'late',revision:1,route:'/late',cause:'initial'}});
  await new Promise(resolve=>setTimeout(resolve,0));
  assert.equal(applied,0,'a late restore cannot flip a module already running its legacy path');
  assert.equal(client.enabled,false);
});
test('retrying a failed handshake starts clean and succeeds once', async () => {
  const clock = manualTimers(), {api,listeners,sent,parent} = sandbox(clock.timers);
  const routes = [];
  const client = api.createClient({apply: async route => {routes.push(route);}});
  const first = client.start({navigation:{versions:[1]}});
  for (let i = 0; i < 5; i++) clock.tick();
  await assert.rejects(first,/timed out/);
  const before = sent.length;
  const second = client.start({navigation:{versions:[1]}});
  assert.equal(sent.length,before + 1,'the attempt counter was reset');
  assert.equal(client.status,'handshaking');
  for (let i = 0; i < 4; i++) clock.tick();
  assert.equal(client.status,'handshaking','four more ticks are within a fresh attempt budget');
  listeners.get('message')({source:parent,origin:'http://localhost',data:{channel:api.channel,type:'restore',document:sent[0].message.document,session:'s',revision:1,route:'/people',cause:'initial'}});
  assert.equal(client.enabled,true,'enabled as soon as a session exists, so the first apply sees it');
  assert.equal(await second,true);
  assert.deepEqual(routes,['/people']);
  assert.equal(clock.intervals.size,0);
  assert.equal(await client.start({navigation:{versions:[1]}}),true,'start after ready is a no-op');
  assert.deepEqual(routes,['/people']);
});
test('an unsupported host is reported as such and stays on the legacy path', async () => {
  const {api} = sandbox();
  const client = api.createClient({apply: async () => {}});
  assert.equal(await client.start({navigation:{versions:[]}}),false);
  assert.equal(client.status,'unsupported'); assert.equal(client.enabled,false);
});
test('apply outcomes reach the host: not-found stays quiet, a failure is reported', async () => {
  const {api,listeners,sent,parent} = sandbox();
  const outcomes = ['not-found',new Error('boom')];
  const errors = [];
  const client = api.createClient({onError:e=>errors.push(e.message),apply: async () => { const next = outcomes.shift(); if (next instanceof Error) throw next; return next; }});
  const starting = client.start({navigation:{versions:[1]}});
  const hello = sent.at(-1).message;
  const restore = (revision) => listeners.get('message')({source:parent,origin:'http://localhost',data:{channel:api.channel,type:'restore',document:hello.document,session:'s',revision,route:'/x',cause:revision === 1 ? 'initial' : 'traversal'}});
  restore(1);
  assert.equal((await starting),true);
  assert.equal(sent.at(-1).message.status,'not-found');
  restore(2); await new Promise(resolve=>setTimeout(resolve,0));
  assert.equal(sent.at(-1).message.status,'error'); assert.deepEqual(errors,['boom']);
  const {context} = sandbox(), reports = [];
  const hosted = makeHost(sandbox().api,context,{report:message=>reports.push(message)});
  hosted.send({type:'applied',session:hosted.session,revision:1,status:'not-found'}); assert.equal(reports.at(-1),'');
  hosted.send({type:'applied',session:hosted.session,revision:1,status:'error'}); assert.match(reports.at(-1),/could not open/);
  hosted.host.reset();
});
test('view state belongs to one history entry and never enters the URL', () => {
  const {api,context} = sandbox(), {host,send,sent,data,session} = makeHost(api,context);
  const firstEntry = context.history.state.nexusNavigation.entry;
  assert.equal(typeof firstEntry,'string');
  assert.equal(sent.at(-1).viewState,null);
  let base = sent.at(-1).revision;
  send({type:'commit',session,baseRevision:base,mode:'push',route:'/people',viewState:{q:'private-text'}});
  const secondEntry = context.history.state.nexusNavigation.entry;
  assert.notEqual(secondEntry,firstEntry,'a pushed entry has its own identity');
  assert.equal(String(context.location).includes('private'),false);
  assert.equal(sent.at(-1).viewState,undefined,'a commit echo carries no state');
  const key = 'nexus.navigation.views.v1:owner:pilot';
  assert.deepEqual(JSON.parse(data.get(key))[firstEntry],{q:'private-text'});
  base = sent.at(-1).revision;
  send({type:'commit',session,baseRevision:base,mode:'replace',route:'/people?x=1',viewState:{scroll:9}});
  assert.equal(context.history.state.nexusNavigation.entry,secondEntry,'a replaced entry keeps its identity');
  // Traversal back: the browser entry has already changed when the host reads it.
  context.history.state = {nexusNavigation:{version:1,entry:firstEntry}};
  host.restore('traversal');
  assert.deepEqual(JSON.parse(JSON.stringify(sent.at(-1).viewState)),{q:'private-text'});
  host.clearDrafts();
  assert.equal(data.has(key),false,'sign-out clears view state');
  host.reset();
});
test('view state is attributed to the entry on screen, bounded, and refused when stale', async () => {
  const {api,context} = sandbox(), {host,send,sent,data,session} = makeHost(api,context);
  const key = 'nexus.navigation.views.v1:owner:pilot', shown = context.history.state.nexusNavigation.entry;
  const leaving = host.prepareLeave();
  const prepare = sent.at(-1);
  context.history.state = {nexusNavigation:{version:1,entry:'the-new-entry'}}; // popstate happened first
  send({type:'prepared',session,id:prepare.id,viewState:{scroll:42}});
  await leaving;
  assert.deepEqual(JSON.parse(data.get(key)),{[shown]:{scroll:42}});
  host.restore('traversal');
  const revision = sent.at(-1).revision;
  send({type:'view-state',session,revision:revision - 1,value:{scroll:1}});
  assert.equal(JSON.parse(data.get(key))['the-new-entry'],undefined,'a state from before the restore is dropped');
  send({type:'view-state',session,revision,value:{big:'x'.repeat(17 * 1024)}});
  assert.equal(JSON.parse(data.get(key))['the-new-entry'],undefined,'over the per-entry bound');
  for (let i = 0; i < 45; i++) host.writeEntryView('pilot','e' + i,{i});
  const views = JSON.parse(data.get(key));
  assert.equal(Object.keys(views).length,40,'only the most recent entries are kept');
  assert.equal(views.e44.i,44); assert.equal(views.e0,undefined);
  host.reset();
});
test('client sends the private view with commits and prepared acknowledgments, never while applying', async () => {
  const {api,listeners,sent,parent} = sandbox();
  let release, captures = 0;
  const client = api.createClient({captureView:()=>{captures++;return {scroll:7};},apply:()=>new Promise(resolve=>{release=resolve;})});
  const starting = client.start({navigation:{versions:[1]}});
  const hello = sent.at(-1).message;
  const message = data => listeners.get('message')({source:parent,origin:'http://localhost',data:{channel:api.channel,...data}});
  message({type:'restore',document:hello.document,session:'s',revision:1,route:'/a',cause:'initial'});
  message({type:'prepare-leave',session:'s',revision:2,id:'early'});
  await new Promise(resolve=>setTimeout(resolve,0));
  assert.equal(sent.at(-1).message.type,'prepared'); assert.equal(sent.at(-1).message.viewState,undefined,'nothing is captured mid-restore');
  assert.equal(captures,0);
  release();
  message({type:'restore',document:hello.document,session:'s',revision:3,route:'/a',cause:'traversal'});
  release?.();
  await new Promise(resolve=>setTimeout(resolve,0)); release?.(); await starting;
  const pending = client.navigate('/b');
  assert.deepEqual(sent.at(-1).message.viewState,{scroll:7});
  message({type:'reject',session:'s',code:'stale'}); await assert.rejects(pending,/rejected/);
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
