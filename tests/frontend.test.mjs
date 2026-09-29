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
async function harness(path='/app/overview', update={status:'not_checked',discovery_supported:false}) {
  const dom = new JSDOM(html, {url:'http://localhost:12333'+path});
  const names=['window','document','location','history','fetch','CSS','getComputedStyle'];
  const saved=Object.fromEntries(names.map(name=>[name,globalThis[name]]));
  Object.assign(globalThis,{window:dom.window,document:dom.window.document,location:dom.window.location,history:dom.window.history,CSS:{escape:value=>value},getComputedStyle:dom.window.getComputedStyle.bind(dom.window)});
  dom.window.matchMedia=()=>({matches:true});
  dom.window.HTMLDialogElement.prototype.showModal=function(){this.open=true;};
  dom.window.HTMLDialogElement.prototype.close=function(){this.open=false;};
  const calls=[];
  const records=[{id:1,source:'nexus',message:'Recorded operational notice',created_at:'2026-09-29T12:00:00Z',read:0}];
  const modules=[{id:'test-module',state:'enabled',health:'healthy',manifest:{id:'test-module',name:'Test module',version:'1.0.0',routes:{api:'/api'},capabilities:[]},provenance:{status:'community'}}];
  globalThis.fetch=async (url,options={})=>{
    calls.push([url,options.method||'GET']);
    // EasyPrivacy: /api/v1/activity|$~third-party,xmlhttprequest
    if (new URL(url, location.origin).href.endsWith('/api/v1/activity')) {
      throw new TypeError('NetworkError when attempting to fetch resource.');
    }
    let data;
    if(url==='/api/v1/setup')data={required:false};
    else if(url==='/api/v1/auth/session')data={username:'owner',csrf:'test-token'};
    else if(url==='/api/v1/system')data={name:'Test installation',version:'0.1.1',data_free_bytes:1024,protocol:1,update};
    else if(url==='/api/v1/modules')data=modules;
    else if(url==='/api/v1/notifications')data=records;
    else if(url==='/api/v1/notifications/read'){records[0].read=1;data={ok:true};}
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
