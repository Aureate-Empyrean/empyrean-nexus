// Loopback-only fixture. No Nexus imports, production assets, credentials or APIs.
import http from 'node:http';
import { readFile } from 'node:fs/promises';
const protocol = (await readFile(new URL('./protocol.mjs', import.meta.url), 'utf8')).replaceAll('export ', '');
const host = `
<h1>Nexus navigation fixture</h1>
<a href="/app/modules/fixture-alpha?keep=yes" data-module>Alpha</a>
<a href="/app/modules/fixture-beta" data-module>Beta</a>
<a href="/app/modules/legacy-old?path=%2Fexisting" data-module>Legacy</a>
<p id="status"></p><div id="mount"></div>
<script type="module">${protocol}
let binding, frame, mountedKey;
window.proof = { restores:0, rejects:0, mounts:0 };
function send(cause) {
  if (!binding?.document) return;
  const message = binding.restore(readEnvelope(location.href).route, cause);
  frame.contentWindow.postMessage(message, '*');
  proof.restores++;
}
function reconcile(cause) {
  try {
    const target = readEnvelope(location.href);
    if (!target) throw Error('Unknown fixture view');
    const key = target.module + target.path;
    if (key !== mountedKey) {
      frame?.remove();
      frame = document.createElement('iframe');
      frame.sandbox = 'allow-scripts allow-downloads';
      frame.title = target.module;
      frame.src = '/modules/' + target.module + target.path;
      document.querySelector('#mount').replaceChildren(frame);
      binding = new FrameSession(frame.contentWindow, target.route);
      mountedKey = key;
      proof.mounts++;
    } else send(cause);
    document.querySelector('#status').textContent = target.module;
  } catch (error) { document.querySelector('#status').textContent = error.message; }
}
document.addEventListener('click', event => {
  const link = event.target.closest('[data-module]');
  if (!link) return;
  event.preventDefault();
  history.pushState({ ...history.state, nexusNavigation: { version:1 } }, '', link.href);
  reconcile('switch');
});
window.addEventListener('popstate', () => reconcile('traversal'));
window.addEventListener('message', event => {
  const result = binding?.receive(event.source, event.data);
  if (!result) return;
  if (result.type === 'hello') return send('initial');
  if (result.type === 'invalid') { proof.rejects++; return; }
  if (result.type === 'stale') { proof.rejects++; return send('resync'); }
  const next = writeEnvelope(location.href, result.route);
  if (next !== location.pathname + location.search + location.hash)
    history[result.mode === 'push' ? 'pushState' : 'replaceState'](
      { ...history.state, nexusNavigation: { version:1 } }, '', next);
  send('commit');
});
window.addEventListener('pageshow', event => { if (event.persisted) reconcile('resume'); });
reconcile('initial');
</script>`;
const child = `
<h2 id="view">Waiting for host</h2>
<button data-route="/list">List</button>
<button data-route="/item/42?tab=notes#recent">Item</button>
<button data-route="/slow">Slow</button>
<button data-route="/filter?q=calendar" data-mode="replace">Filter</button>
<script type="module">${protocol}
const documentId = crypto.randomUUID();
let session, revision = 0, paintToken = 0;
window.fixture = { applied:0, last:null };
window.addEventListener('message', event => {
  const message = event.data;
  if (event.source !== parent || event.origin !== location.origin ||
      message?.channel !== CHANNEL || message.type !== 'restore' ||
      message.document !== documentId || (session && message.session !== session) ||
      message.revision < revision) return;
  session = message.session;
  revision = message.revision;
  fixture.last = message;
  const token = ++paintToken;
  const paint = () => {
    if (token !== paintToken) return;
    document.querySelector('#view').textContent = message.route;
    fixture.applied++;
    parent.postMessage({channel:CHANNEL,type:'applied',session,revision,status:'ok'}, location.origin);
  };
  if (message.route === '/slow') setTimeout(paint, 250); else paint();
});
window.intent = (route, mode = 'push', baseRevision = revision) =>
  parent.postMessage({channel:CHANNEL,type:'commit',session,baseRevision,route,mode}, location.origin);
document.addEventListener('click', event => {
  const target = event.target.closest('[data-route]');
  if (target && session) intent(target.dataset.route, target.dataset.mode || 'push');
});
parent.postMessage({channel:CHANNEL,type:'hello',version:1,document:documentId}, location.origin);
</script>`;
const csp = "sandbox allow-scripts allow-downloads; default-src 'none'; style-src 'unsafe-inline'; img-src data:; font-src data:; script-src 'unsafe-inline'; connect-src 'none'; form-action 'none'; base-uri 'none'; frame-ancestors 'self'";
const server = http.createServer((req, res) => {
  const url = new URL(req.url, 'http://127.0.0.1');
  const isChild = url.pathname.startsWith('/modules/');
  res.writeHead(200, { 'Content-Type':'text/html; charset=utf-8', 'Cache-Control':'no-store',
    ...(isChild ? {'Content-Security-Policy':csp} : {}) });
  res.end('<!doctype html><meta charset="utf-8">' + (isChild ?
    (url.pathname.startsWith('/modules/legacy-old/') ? '<h2 id="view">Legacy bootstrap: /existing</h2>' : child) : host));
});
server.listen(Number(process.env.NEXUS_PROOF_PORT || 19439), '127.0.0.1', () =>
  console.log('Fixture listening on http://127.0.0.1:' + server.address().port));
