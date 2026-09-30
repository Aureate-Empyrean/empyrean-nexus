import test from 'node:test';
import assert from 'node:assert/strict';
import { matchRoute, createRouter } from '../frontend/router.js';
import { animate, reducedMotion } from '../frontend/motion.js';

test('routes include utility/module views and reject invalid module paths', () => {
  for (const name of ['overview', 'modules', 'activity', 'settings', 'notifications']) {
    assert.equal(matchRoute('/app/' + name).name, name);
  }
  assert.deepEqual(matchRoute('/app/modules/community-module', '?path=%2Fitems%2F42'), { name:'module', id:'community-module', modulePath:'/items/42' });
  assert.equal(matchRoute('/app/modules/community-module', '?path=%2F%2Fevil.test').name, 'not-found');
  assert.equal(matchRoute('/app/modules/community-module', '?path=%2F..%2Fprivate').name, 'not-found');
  assert.equal(matchRoute('/app/guide').name, 'not-found');
  assert.equal(matchRoute('/api/v1/modules').name, 'not-found');
});

test('history preserves back/forward and direct route loading without duplicate entries', () => {
  let listener;
  const entries = ['/'];
  let index = 0;
  globalThis.location = { origin:'http://localhost:12333', pathname:'/', search:'' };
  const set = path => { const url = new URL(path, location.origin); location.pathname = url.pathname; location.search = url.search; };
  globalThis.window = { addEventListener: (name, cb) => { assert.equal(name,'popstate'); listener = cb; } };
  globalThis.history = {
    replaceState: (_state,_title,path) => { entries[index] = path; set(path); },
    pushState: (_state,_title,path) => { entries.splice(index+1); entries.push(path); index++; set(path); },
  };
  let current;
  const router = createRouter(route => { current = route; });
  router.start();
  assert.deepEqual(entries,['/app/overview']);
  router.navigate('/app/modules'); router.navigate('/app/settings');
  router.navigate('/app/settings');
  assert.equal(entries.length,3);
  index--; set(entries[index]); listener(); assert.equal(current.name,'modules');
  index--; set(entries[index]); listener(); assert.equal(current.name,'overview');
  index++; set(entries[index]); listener(); assert.equal(current.name,'modules');
  router.navigate('/app/activity');
  assert.deepEqual(entries,['/app/overview','/app/modules','/app/activity']);
  router.navigate('https://foreign.example/app/settings'); assert.equal(current.name,'activity');
  set('/app/modules/example?path=/items/a'); router.start();
  assert.equal(current.id,'example'); assert.equal(current.modulePath,'/items/a');
});

test('reduced motion skips animation and does not delay the operation', async () => {
  globalThis.window = { matchMedia: () => ({matches:true}) };
  let called = false;
  await animate({animate: () => {called=true;}}, []);
  assert.equal(reducedMotion(),true); assert.equal(called,false);
});

test('motion cancels superseded animation and safely settles interrupted promises', async () => {
  globalThis.window = { matchMedia: () => ({matches:false}) };
  globalThis.document = { documentElement:{} };
  globalThis.getComputedStyle = () => ({getPropertyValue: () => ''});
  const calls=[];
  const element={ animate: (frames,options) => {
    let resolve, reject;
    const finished=new Promise((ok,fail)=>{resolve=ok;reject=fail;});
    const animation={finished,cancel:()=>reject(new Error('cancelled')),resolve,options};
    calls.push(animation); return animation;
  }};
  const first=animate(element,[{}]);
  const second=animate(element,[{}]);
  calls[1].resolve();
  await Promise.all([first,second]);
  assert.equal(calls[1].options.duration,200);
  assert.equal(calls[1].options.fill,'backwards');
});

const { JSDOM } = await import('jsdom');
const { readFile } = await import('node:fs/promises');
const html = await readFile(new URL('../frontend/index.html', import.meta.url), 'utf8');
const realTimeout = globalThis.setTimeout;
async function until(predicate) {
  for (let i=0; i<80; i++) { if (predicate()) return; await new Promise(resolve => realTimeout(resolve, 5)); }
  assert.fail('UI state did not settle');
}
let harnessCount=0;
async function harness(path='/app/overview', update={status:'not_checked',discovery_supported:false}, capabilities=[], systemExtra={}, moreModules=[]) {
  const dom = new JSDOM(html, {url:'http://localhost:12333'+path});
  const names=['window','document','location','history','fetch','CSS','getComputedStyle'];
  const saved=Object.fromEntries(names.map(name=>[name,globalThis[name]]));
  Object.assign(globalThis,{window:dom.window,document:dom.window.document,location:dom.window.location,history:dom.window.history,CSS:{escape:value=>value},getComputedStyle:dom.window.getComputedStyle.bind(dom.window)});
  dom.window.matchMedia=()=>({matches:true});
  dom.window.HTMLDialogElement.prototype.showModal=function(){this.open=true;};
  dom.window.HTMLDialogElement.prototype.close=function(){this.open=false;};
  const calls=[];
  const records=[{id:1,source:'nexus',message:'Recorded operational notice',created_at:'2026-09-29T12:00:00Z',read:0}];
  const modules=[{id:'test-module',state:'enabled',health:'healthy',manifest:{id:'test-module',name:'Test module',version:'1.0.0',routes:{api:'/api'},capabilities},provenance:{status:'community'},external_origins:[]},...moreModules];
  globalThis.fetch=async (url,options={})=>{
    calls.push([url,options.method||'GET']);
    // EasyPrivacy: /api/v1/activity|$~third-party,xmlhttprequest
    if (new URL(url, location.origin).href.endsWith('/api/v1/activity')) {
      throw new TypeError('NetworkError when attempting to fetch resource.');
    }
    let data;
    if(url==='/api/v1/setup')data={required:false};
    else if(url==='/api/v1/auth/session')data={username:'owner',csrf:'test-token'};
    else if(url==='/api/v1/system')data={name:'Test installation',version:'0.1.1',data_free_bytes:1024,protocol:1,update,...systemExtra};
    else if(url==='/api/v1/modules')data=modules;
    else if(url==='/api/v1/notifications')data=records;
    else if(url==='/api/v1/notifications/read'){records[0].read=1;data={ok:true};}
    else if(/^\/api\/v1\/modules\/[a-z-]+\/external-origins$/.test(url)&&options.method==='POST'){const id=url.split('/')[4];const m=modules.find(x=>x.id===id);m.external_origins=[...m.external_origins,JSON.parse(options.body).origin];data={module:id,external_origins:m.external_origins};}
    else if(url==='/api/v1/activity/entries')data={items:[{id:2,kind:'module.enable.completed',subject:'test-module',actor:'owner',occurred_at:'2026-09-29T12:00:00Z'}],next_cursor:2,has_more:true};
    else if(url==='/api/v1/activity/entries?before=2')data={items:[{id:1,kind:'setup.completed',subject:'nexus',actor:'owner',occurred_at:'2026-09-29T11:00:00Z'}],next_cursor:1,has_more:false};
    else throw new Error('Unexpected test request '+url);
    return {ok:true,status:200,json:async()=>structuredClone(data)};
  };
  await import('../frontend/app.js?dom-test='+harnessCount++);
  await until(()=>document.querySelector('.shell'));
  return {dom,calls,close:()=>{dom.window.close();Object.assign(globalThis,saved);}};
}

test('rendered navigation uses real routes and separates utilities/app switcher', async()=>{
  const h=await harness();
  try {
    assert.deepEqual([...document.querySelectorAll('.nav a')].map(a=>a.textContent.trim().replace(/^[^a-zA-Z]+/,'')),['Overview','Modules','Activity']);
    assert.equal(document.querySelector('.utility-nav a').textContent.trim(),'⚙ Settings');
    assert.equal(document.querySelector('.sidebar').textContent.includes('Locally hosted'),false);
    assert.equal(document.querySelector('.sidebar').textContent.includes('Guide'),false);
    document.querySelector('[data-nav=modules]').click();
    assert.equal(location.pathname,'/app/modules');
    document.querySelector('[data-nav=settings]').click();
    assert.equal(location.pathname,'/app/settings');
    history.back();await until(()=>location.pathname==='/app/modules');
    assert.equal(document.querySelector('#content h1').textContent,'Modules');
    history.forward();await until(()=>location.pathname==='/app/settings');
    assert.equal(document.querySelector('#content h1').textContent,'Settings');
    document.querySelector('#product-switch').click();
    assert.equal(document.querySelector('#product-menu').hidden,false);
    assert.equal(document.querySelectorAll('#product-menu a').length,3);
    document.querySelector('#product-menu a[href="/app/modules/test-module"]').click();
    assert.equal(location.pathname,'/app/modules/test-module');
    assert.equal(document.querySelector('iframe').getAttribute('sandbox'),'allow-scripts');
  } finally {h.close();}
});

test('notification center refreshes data, marks read and closes with Escape', async()=>{
  const h=await harness('/app/settings');
  try {
    assert.equal(document.querySelector('#content h1').textContent,'Settings');
    document.querySelector('#bell').click();
    await until(()=>!document.querySelector('#notification-panel').hidden);
    assert.match(document.querySelector('#notification-panel').textContent,/Recorded operational notice/);
    assert.equal(document.querySelector('#bell').getAttribute('aria-expanded'),'true');
    document.querySelector('#panel-read-action button').click();
    await until(()=>document.querySelector('#unread-indicator').hidden);
    document.dispatchEvent(new window.KeyboardEvent('keydown',{key:'Escape',bubbles:true}));
    await until(()=>document.querySelector('#notification-panel').hidden);
    assert.equal(document.querySelector('#bell').getAttribute('aria-expanded'),'false');
    assert.ok(h.calls.filter(([path])=>path==='/api/v1/notifications').length>=3);
  } finally {h.close();}
});

test('release controls never invent an update or execute one', async()=>{
  let h=await harness();
  try {
    assert.equal(document.querySelector('#update-card'),null);
    document.querySelector('#version-button').click();
    assert.match(document.querySelector('#dialog').textContent,/not configured/);
    assert.equal(document.querySelector('#dialog').textContent.includes('Up to date'),false);
  } finally {h.close();}
  h=await harness('/app/overview',{status:'available',discovery_supported:true,version:'0.2.0',notes:'A test release',url:'https://example.org/releases/0.2.0'});
  try {
    document.querySelector('#update-card').click();
    assert.match(document.querySelector('#dialog').textContent,/0\.2\.0/);
    assert.equal(h.calls.some(([,method])=>method!=='GET'),false);
  } finally {h.close();}
});

test('Activity loads, paginates and refreshes with the EasyPrivacy endpoint filter active', async()=>{
  const h=await harness('/app/activity');
  try {
    await until(()=>document.querySelector('.activity-row'));
    assert.match(document.querySelector('.activity-row').textContent,/Enable · completed/);
    assert.equal(document.querySelectorAll('.activity-row').length,1);
    document.querySelector('#activity-more button').click();
    await until(()=>document.querySelectorAll('.activity-row').length===2);
    assert.match(document.querySelector('#activity-list').textContent,/Installation initialized/);
    assert.equal(document.querySelector('#activity-more button'),null);
    document.querySelector('#heading-action button').click();
    await until(()=>document.querySelectorAll('.activity-row').length===1);
    assert.equal(h.calls.filter(([path])=>path==='/api/v1/activity/entries').length,2);
    assert.ok(h.calls.some(([path])=>path==='/api/v1/activity/entries?before=2'));
    assert.equal(document.querySelector('[role=alert]'),null);
    assert.equal(document.querySelector('.nav').textContent.includes('Test module'),false);
  } finally {h.close();}
});

test('uninstall review states that persistent module data is retained, not deleted', async()=>{
  let h=await harness('/app/modules',undefined,['storage.data']);
  try {
    await until(()=>document.querySelector('[data-module-id="test-module"]'));
    [...document.querySelectorAll('[data-module-id="test-module"] button')].find(b=>b.textContent==='Uninstall').click();
    const text=document.querySelector('#dialog').textContent;
    assert.match(text,/persistent data volume is retained, not deleted/);
    assert.equal(text.includes('disposable'),false);
    assert.equal(h.calls.some(([,method])=>method==='DELETE'),false);
  } finally {h.close();}
  h=await harness('/app/modules');
  try {
    await until(()=>document.querySelector('[data-module-id="test-module"]'));
    [...document.querySelectorAll('[data-module-id="test-module"] button')].find(b=>b.textContent==='Uninstall').click();
    assert.match(document.querySelector('#dialog').textContent,/declares no persistent storage/);
  } finally {h.close();}
});

test('reference manifest loading is a development-only action', async()=>{
  let h=await harness('/app/modules');
  try {
    document.querySelector('#heading-action button.primary').click();
    assert.equal([...document.querySelectorAll('#dialog button')].some(b=>b.textContent==='Load reference manifest'),false);
  } finally {h.close();}
  h=await harness('/app/modules',undefined,[],{development:{reference_module:true}});
  try {
    document.querySelector('#heading-action button.primary').click();
    assert.ok([...document.querySelectorAll('#dialog button')].some(b=>b.textContent==='Load reference manifest'));
  } finally {h.close();}
});

async function bridgeHarness(path='/app/modules/test-module') {
  const other={id:'other-module',state:'enabled',health:'healthy',manifest:{id:'other-module',name:'Other module',version:'1.0.0',routes:{api:'/api'},capabilities:['ui.application']},provenance:{status:'community'},external_origins:[]};
  const h=await harness(path,undefined,['ui.application'],{},[other]);
  await until(()=>document.querySelector('#module-application'));
  const opened=[], replies=[];
  window.open=(...args)=>{opened.push(args);return null;};
  const frame=()=>document.querySelector('#module-application');
  const send=(id,url)=>{const f=frame();f.contentWindow.postMessage=data=>replies.push(data);window.dispatchEvent(new window.MessageEvent('message',{data:{channel:'empyrean-v1',id,action:'external',url},source:f.contentWindow}));};
  const reply=async id=>{await until(()=>replies.some(r=>r.id===id));return replies.find(r=>r.id===id);};
  const armed=async()=>{await until(()=>document.querySelector('#external-actions'));await new Promise(r=>realTimeout(r,700));return document.querySelectorAll('#external-actions button');};
  return {...h,opened,send,reply,armed,posts:()=>h.calls.filter(([u,m])=>m==='POST'&&u.includes('external-origins'))};
}

test('bridge trust is granted to an origin, and granting it transmits nothing (A, B)', async()=>{
  const h=await bridgeHarness();
  try {
    const exfil='https://evil.example/collect/secret-path?notes=private%20data#frag';
    h.send('first',exfil);
    const [cancel,trust]=await h.armed();
    // The owner sees the origin being trusted, not a link to click through.
    assert.equal(document.querySelector('#external-origin').textContent,'https://evil.example');
    assert.equal(document.querySelector('#dialog').textContent.includes('secret-path'),false);
    assert.equal(document.querySelector('#dialog').textContent.includes('private'),false);
    assert.match(document.querySelector('#dialog').textContent,/Test module/);
    trust.click();
    const answer=await h.reply('first');
    assert.deepEqual(answer.result,{opened:false,trusted:true});
    assert.deepEqual(h.opened,[],'trusting must not navigate to the requested URL');
    assert.deepEqual(h.posts().map(([u])=>u),['/api/v1/modules/test-module/external-origins']);
  } finally {h.close();}
});

test('a trusted origin opens directly; other scheme, host, port or lookalike does not (C, E)', async()=>{
  const h=await bridgeHarness();
  try {
    h.send('trust','https://docs.example.org/start');
    (await h.armed())[1].click();
    await h.reply('trust');
    const target='https://docs.example.org/guide/page?section=2#top';
    h.send('open',target);
    assert.deepEqual((await h.reply('open')).result,{opened:true});
    assert.deepEqual(h.opened,[[target,'_blank','noopener,noreferrer']]);
    for (const [id,url,origin] of [['http','http://docs.example.org/guide','http://docs.example.org'],['port','https://docs.example.org:8443/guide','https://docs.example.org:8443'],['sub','https://evil.docs.example.org/','https://evil.docs.example.org'],['suffix','https://docs.example.org.evil.example/','https://docs.example.org.evil.example'],['lookalike','https://docs.exаmple.org/','https://docs.xn--exmple-4nf.org']]) {
      h.send(id,url);
      await until(()=>document.querySelector('#external-origin'));
      assert.equal(document.querySelector('#external-origin').textContent,origin,id);
      assert.equal(h.opened.length,1,id);
      document.querySelectorAll('#external-actions button')[0].click();
      assert.match((await h.reply(id)).error,/not trusted/);
    }
  } finally {h.close();}
});

test('trust granted to one module does not apply to another (D)', async()=>{
  const h=await bridgeHarness();
  try {
    h.send('a','https://shared.example/x');
    (await h.armed())[1].click();
    await h.reply('a');
    document.querySelector('#product-switch').click();
    document.querySelector('#product-menu a[href="/app/modules/other-module"]').click();
    await until(()=>document.querySelector('#module-application')?.getAttribute('src')?.startsWith('/modules/other-module'));
    h.send('b','https://shared.example/x');
    await until(()=>document.querySelector('#external-origin'));
    assert.match(document.querySelector('#dialog').textContent,/Other module/);
    assert.equal(h.opened.length,0);
    document.querySelectorAll('#external-actions button')[0].click();
    assert.match((await h.reply('b')).error,/not trusted/);
  } finally {h.close();}
});

test('credentials, unsupported schemes and oversized or relative links are rejected (F)', async()=>{
  const h=await bridgeHarness();
  try {
    for (const [id,url] of [['js','javascript:alert(1)'],['data','data:text/html,x'],['file','file:///etc/passwd'],['ftp','ftp://files.example/'],['creds','https://user:pw@evil.example/'],['user','https://user@evil.example/'],['long','https://evil.example/?'+'a'.repeat(3000)],['relative','/relative'],['mailbad','mailto:a@b.example,c@d.example']]) {
      h.send(id,url);
      assert.ok((await h.reply(id)).error,id);
      assert.equal(document.querySelector('#dialog').open,false,id);
    }
    assert.deepEqual(h.opened,[]);
    assert.deepEqual(h.posts(),[]);
  } finally {h.close();}
});

test('mailto opens only the reviewed address and never module-supplied content (G)', async()=>{
  const h=await bridgeHarness();
  try {
    h.send('mail','mailto:friend@example.org?subject=hi&body=private%20notes&bcc=spy@evil.example');
    const [cancel,start]=await h.armed();
    assert.equal(document.querySelector('#external-origin').textContent,'friend@example.org');
    assert.match(document.querySelector('#dialog').textContent,/discarded/);
    assert.equal(document.querySelector('#dialog').textContent.includes('private notes'),false);
    start.click();
    assert.deepEqual((await h.reply('mail')).result,{opened:true});
    assert.deepEqual(h.opened,[['mailto:friend@example.org','_blank','noopener,noreferrer']]);
    // Mail never becomes a standing trust: the next request asks again.
    h.send('again','mailto:friend@example.org');
    await until(()=>document.querySelector('#external-origin'));
    assert.equal(h.opened.length,1);
    assert.deepEqual(h.posts(),[]);
    document.querySelectorAll('#external-actions button')[0].click();
    assert.match((await h.reply('again')).error,/not started/);
  } finally {h.close();}
});

test('trust decisions cannot be clicked through or stacked', async()=>{
  const h=await bridgeHarness();
  try {
    h.send('pending','https://new.example/');
    await until(()=>document.querySelector('#external-actions'));
    const trust=document.querySelectorAll('#external-actions button')[1];
    assert.equal(trust.disabled,true);
    trust.click();
    assert.deepEqual(h.posts(),[]);
    h.send('stacked','https://other.example/');
    assert.match((await h.reply('stacked')).error,/waiting/);
    document.querySelectorAll('#external-actions button')[0].click();
    assert.match((await h.reply('pending')).error,/not trusted/);
    assert.deepEqual(h.opened,[]);
  } finally {h.close();}
});
