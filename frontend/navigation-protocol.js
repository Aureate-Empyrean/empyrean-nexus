/* Empyrean Navigation v1. Dependency-free; also bundled inline in opaque modules.
 * Source of truth: Nexus. Sync vendored copies with scripts/sync-navigation.mjs.
 * No API credentials, module domain state or draft text belongs in route URLs.
 */
(() => {
  const channel = 'empyrean-navigation-v1';
  // getRandomValues also works on existing HTTP LAN installations; randomUUID
  // would require a secure context and break feature-disabled legacy modules.
  const nonce = () => Array.from(crypto.getRandomValues(new Uint8Array(16)),
    value => value.toString(16).padStart(2,'0')).join('');
  const bytes = value => new TextEncoder().encode(value).length;
  function route(value) {
    if (typeof value !== 'string' || !value.startsWith('/') || value.startsWith('//') ||
        bytes(value) > 2048 || /[\s\\\u0000-\u001f\u007f]/u.test(value) || /%(?![a-f\d]{2})/i.test(value))
      throw Error('Invalid navigation route');
    const path = value.split(/[?#]/, 1)[0];
    let decoded;
    try { decoded = decodeURIComponent(path); } catch { throw Error('Invalid route encoding'); }
    if (/[\\\u0000-\u0020\u007f]/u.test(decoded) || /%2f|%5c/i.test(path) ||
        decoded.split('/').some(part => part === '.' || part === '..')) throw Error('Invalid route path');
    return value;
  }
  function envelope(search) {
    const params = new URLSearchParams(search);
    if (!params.has('nav') && !params.has('route')) return null;
    if (['path', 'nav', 'route'].some(key => params.getAll(key).length > 1) ||
        params.get('nav') !== '1' || !params.has('route')) throw Error('Invalid navigation envelope');
    return route(params.get('route'));
  }
  function urlFor(input, value) {
    const url = new URL(input);
    url.searchParams.set('nav', '1');
    url.searchParams.set('route', route(value));
    return url.pathname + url.search + url.hash;
  }
  function createHost({ active, current, commit, report, storage, owner }) {
    if (!storage) {
      try { storage = window.sessionStorage; }
      catch { storage = {getItem:() => null, setItem:() => {throw Error('Storage unavailable');}, length:0}; }
    }
    let binding = null;
    const key = module => 'nexus.navigation.drafts.v1:' + owner() + ':' + module;
    function snapshot(module) {
      try { return JSON.parse(storage.getItem(key(module)) || 'null'); } catch { return null; }
    }
    function post(message) {
      if (binding?.frame.isConnected) binding.frame.contentWindow.postMessage({channel, ...message}, '*');
    }
    function restore(cause = 'traversal') {
      if (!binding?.document) return;
      clearTimeout(binding.timer);
      const target = current();
      binding.leaving = false;
      post({type:'restore', document:binding.document, session:binding.session,
        revision:++binding.revision, route:target.navigationRoute ?? target.modulePath,
        legacy:target.navigationRoute === undefined, cause,
        ...(cause === 'initial' ? {checkpoint:snapshot(binding.module)} : {})});
      const revision = binding.revision;
      binding.timer = setTimeout(() => {
        if (binding?.revision === revision) report('The application has not restored this view. Reload to retry.');
      }, 20000);
    }
    function bind(frame, module) {
      if (binding?.frame === frame && binding.module === module) return;
      clearTimeout(binding?.timer);
      binding?.frame.removeEventListener?.('load', binding.loaded);
      binding = {frame, module, revision:0, windowStart:Date.now(), count:0,challenge:nonce()};
      binding.loaded = () => {
        if (binding?.frame !== frame) return;
        clearTimeout(binding.timer);
        binding.challenge = nonce(); binding.document = null; binding.session = null;
        post({type:'probe',challenge:binding.challenge});
      };
      frame.addEventListener?.('load', binding.loaded);
    }
    function reset() {
      clearTimeout(binding?.timer);
      clearTimeout(binding?.leavingTimer);
      binding?.leave?.resolve();
      binding?.frame.removeEventListener?.('load', binding.loaded);
      binding = null; report('');
    }
    function reject(code) {
      post({type:'reject',session:binding.session,revision:binding.revision,code});
    }
    function receive(event) {
      if (!binding || !binding.frame.isConnected || event.source !== binding.frame.contentWindow ||
          !active(binding.module)) return;
      const m = event.data;
      if (!m || typeof m !== 'object' || m.channel !== channel) return;
      if (m.type === 'hello') {
        if (m.version !== 1 || typeof m.document !== 'string' || !/^[\w-]{1,100}$/.test(m.document)) return;
        if (m.challenge !== binding.challenge) { post({type:'probe',challenge:binding.challenge}); return; }
        if (binding.document !== m.document) {
          binding.document = m.document; binding.session = nonce();
        }
        restore('initial');
        return;
      }
      if (!binding.document || m.session !== binding.session) return;
      if (m.type === 'prepared') {
        if (!binding.leave || m.id !== binding.leave.id) return;
        clearTimeout(binding.leavingTimer);
        const pending = binding.leave; binding.leave = null;
        if (m.error) { binding.leaving = false; pending.reject(Error('Draft checkpoint failed. The editor remains open for recovery.')); }
        else pending.resolve();
        return;
      }
      if (m.type === 'checkpoint') {
        if (!Number.isSafeInteger(m.id) || m.id < 1) return;
        if (!binding.checkpointStart || Date.now() - binding.checkpointStart > 1000) {
          binding.checkpointStart = Date.now(); binding.checkpointCount = 0;
        }
        if (++binding.checkpointCount > 100) {
          post({type:'checkpointed',session:binding.session,id:m.id,error:'Draft checkpoints are arriving too quickly. Save before leaving.'});
          return;
        }
        try {
          if (!m.value || typeof m.value !== 'object' || Array.isArray(m.value)) throw Error('Invalid checkpoint');
          const serialized = JSON.stringify(m.value);
          if (bytes(serialized) > 1024 * 1024) throw Error('Draft checkpoint too large');
          storage.setItem(key(binding.module), serialized);
          post({type:'checkpointed',session:binding.session,id:m.id});
        } catch { post({type:'checkpointed',session:binding.session,id:m.id,error:'Draft recovery storage is unavailable or full. Save before leaving.'}); }
        return;
      }
      if (m.type === 'applied') {
        if (m.revision !== binding.revision || !['ok','not-found','error'].includes(m.status)) return;
        clearTimeout(binding.timer);
        report(m.status === 'ok' ? '' : 'The application could not open this view. The address has been retained.');
        return;
      }
      if (m.type !== 'commit') return;
      if (binding.leaving) return reject('leaving');
      if (Date.now() - binding.windowStart > 1000) { binding.windowStart = Date.now(); binding.count = 0; }
      if (++binding.count > 40) return reject('rate-limit');
      if (m.baseRevision !== binding.revision) { reject('stale'); restore('resync'); return; }
      try {
        if (!['push','replace'].includes(m.mode)) throw Error('Invalid history mode');
        const next = urlFor(location.href, m.route);
        const previous = location.pathname + location.search + location.hash;
        if (next !== previous) {
          history[m.mode === 'push' ? 'pushState' : 'replaceState'](
            {...history.state, nexusNavigation:{version:1}}, '', next);
          commit(m.route);
        }
        restore('commit');
      } catch { reject('invalid-route'); }
    }
    function prepareLeave() {
      if (!binding?.document || !active(binding.module)) return Promise.resolve();
      if (binding.leave) return binding.leave.promise;
      let resolve, reject;
      const promise = new Promise((ok, fail) => {resolve=ok;reject=fail;});
      const id = nonce();
      binding.leave = {id,promise,resolve,reject}; binding.leaving = true;
      binding.leavingTimer = setTimeout(() => {
        if (!binding?.leave || binding.leave.id !== id) return;
        binding.leave = null; binding.leaving = false;
        reject(Error('The application could not checkpoint its drafts. Its editor remains open.'));
      }, 5000);
      post({type:'prepare-leave',session:binding.session,revision:++binding.revision,id});
      return promise;
    }
    function hasDrafts() {
      const prefix = 'nexus.navigation.drafts.v1:' + owner() + ':';
      for (let i = 0; i < storage.length; i++) {
        const name = storage.key(i);
        if (name?.startsWith(prefix)) {
          try { if (JSON.parse(storage.getItem(name))?.dirty === true) return true; } catch { /* no readable checkpoint */ }
        }
      }
      return false;
    }
    return {bind, restore, reset, receive, prepareLeave, hasDrafts, clearModuleDrafts(module) { storage.removeItem?.(key(module)); }, clearDrafts() {
      const prefix = 'nexus.navigation.drafts.v1:' + owner() + ':';
      for (let i = storage.length - 1; i >= 0; i--) {
        const name = storage.key(i); if (name?.startsWith(prefix)) storage.removeItem(name);
      }
    }};
  }
  function createClient({ apply, invalidate = () => {}, onError = () => {}, beforeLeave = async () => {} }) {
    const documentId = nonce();
    const parentOrigin = (() => { try { return new URL(document.referrer).origin; } catch { return location.origin; } })();
    let enabled = false, session, revision = 0, target, draining = false, intent, initial, currentRoute, challenge;
    let receipt = 0;
    let sequence = 0, helloTimer, helloAttempts = 0;
    const checkpoints = new Map();
    const post = data => parent.postMessage({channel, ...data}, parentOrigin);
    function failure(error) { onError(error); return error; }
    async function drain() {
      if (draining) return;
      draining = true;
      while (target) {
        const message = target; target = null;
        const token = receipt;
        const isCurrent = () => token === receipt && message.revision === revision && message.session === session;
        let status = 'ok';
        try { await apply(message.route, {...message, isCurrent}); }
        catch (error) { status = 'error'; if (isCurrent()) failure(error); }
        if (!isCurrent()) continue;
        post({type:'applied',session,revision,status});
        initial?.resolve(message); initial = null;
        if (intent && message.cause === 'commit') { intent.resolve(message); intent = null; }
      }
      draining = false;
    }
    window.addEventListener('message', event => {
      const m = event.data;
      if (!enabled || event.source !== parent || event.origin !== parentOrigin || m?.channel !== channel) return;
      if (m.type === 'prepare-leave' && m.session === session) {
        if (!Number.isSafeInteger(m.revision) || m.revision <= revision || typeof m.id !== 'string') return;
        revision = m.revision; ++receipt;
        intent?.reject(Error('Navigation superseded')); intent = null;
        invalidate();
        Promise.resolve().then(beforeLeave).then(
          () => post({type:'prepared',session,id:m.id}),
          () => post({type:'prepared',session,id:m.id,error:true}));
      } else if (m.type === 'probe') {
        if (typeof m.challenge !== 'string' || !/^[\w-]{1,100}$/.test(m.challenge)) return;
        if (challenge !== m.challenge) {
          challenge = m.challenge; session = undefined; revision = 0; ++receipt;
          intent?.reject(Error('Application document changed')); intent = null;
        }
        post({type:'hello',version:1,document:documentId,challenge});
      } else if (m.type === 'restore') {
        if (m.document !== documentId || typeof m.session !== 'string' ||
            (session && session !== m.session) || !Number.isSafeInteger(m.revision) || m.revision <= revision) return;
        try { route(m.route); } catch { return; }
        session = m.session; revision = m.revision; currentRoute = m.route; ++receipt;
        clearInterval(helloTimer);
        if (intent && m.cause !== 'commit') { intent.reject(Error('Navigation superseded')); intent = null; }
        invalidate(); target = m; void drain();
      } else if (m.session === session && m.type === 'reject') {
        intent?.reject(Error('Navigation rejected: ' + m.code)); intent = null;
      } else if (m.session === session && m.type === 'checkpointed') {
        const pending = checkpoints.get(m.id);
        if (!pending) return;
        clearTimeout(pending.timer); checkpoints.delete(m.id);
        if (m.error) pending.reject(failure(Error(m.error))); else pending.resolve();
      }
    });
    function timeout(pending, label) {
      pending.timer = setTimeout(() => pending.reject(failure(Error(label))), 10000);
    }
    return {
      get enabled() { return enabled; },
      get revision() { return revision; },
      get route() { return currentRoute; },
      async start(context) {
        if (!context?.navigation?.versions?.includes(1) || parent === window) return false;
        enabled = true;
        const ready = new Promise((resolve, reject) => { initial = {resolve,reject}; });
        const hello = () => {
          if (++helloAttempts > 5) { clearInterval(helloTimer); initial?.reject(Error('Navigation handshake timed out')); initial = null; return; }
          post({type:'hello',version:1,document:documentId,challenge});
        };
        helloTimer = setInterval(hello, 500); hello();
        await ready; return true;
      },
      navigate(value, mode = 'push') {
        route(value);
        if (!enabled || !session) return Promise.reject(Error('Navigation is not ready'));
        // One outstanding intent. Never rebase an obsolete intent after traversal.
        if (intent) return Promise.reject(Error('Navigation is already pending'));
        return new Promise((resolve, reject) => {
          const pending = {resolve: value => {clearTimeout(pending.timer); resolve(value);},
            reject: error => {clearTimeout(pending.timer); if (intent === pending) intent = null; reject(error);}};
          intent = pending; timeout(pending, 'Navigation acknowledgment timed out');
          post({type:'commit',session,baseRevision:revision,route:value,mode});
        });
      },
      checkpoint(value) {
        if (!enabled || !session) return Promise.resolve();
        return new Promise((resolve, reject) => {
          const id = ++sequence, pending = {resolve,reject};
          checkpoints.set(id, pending); timeout(pending, 'Draft checkpoint timed out');
          post({type:'checkpoint',session,id,value});
        });
      },
    };
  }
  globalThis.EmpyreanNavigation = Object.freeze({version:1, channel, route, envelope, urlFor, createHost, createClient});
})();
