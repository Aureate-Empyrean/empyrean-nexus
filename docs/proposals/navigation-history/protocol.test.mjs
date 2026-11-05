import test from 'node:test';
import assert from 'node:assert/strict';
import { CHANNEL, FrameSession, readEnvelope, writeEnvelope, routeReference } from './protocol.mjs';
const root = 'http://localhost/app/modules/meridian';
test('existing module URLs and first-value legacy path remain valid', () => {
  assert.deepEqual(readEnvelope(root), {module:'meridian', path:'/',route:'/',version:0});
  assert.equal(readEnvelope(root + '?path=%2Fpeople%2Fabc').path, '/people/abc');
  assert.equal(readEnvelope(root + '?path=/one&path=/two').path, '/one');
  assert.equal(readEnvelope('http://localhost/app/overview'), null);
});
test('nested query, fragment and Unicode survive one outer encoding round trip', () => {
  const route = '/people/abc?tab=notes&query=%C5%BElt%C3%BD%26x#recent';
  const next = writeEnvelope(root + '?path=/people/abc&keep=yes', route);
  assert.equal(readEnvelope('http://localhost' + next).route, route);
  assert.equal(readEnvelope('http://localhost' + next).path, '/people/abc');
  assert.equal(new URL(next, root).searchParams.get('keep'), 'yes');
});
test('reject ambiguous envelopes and preserve bootstrap validation', () => {
  for (const query of ['nav=2&route=/one', 'nav=1', 'route=/one',
    'nav=1&route=/one&route=/two', 'nav=1&nav=1&route=/one',
    'nav=1&route=/one&path=/one&path=/two', 'path=//evil', 'path=/a/../b'])
    assert.throws(() => readEnvelope(root + '?' + query), query);
});
test('reject routes that could escape a local reference or contain invalid data', () => {
  for (const route of ['//evil', 'https://evil/', '/a/../b', '/%2e%2e/a', '/a%2fb',
    '/a%5cb', '/a\\b', '/a\nb', '/a b', '/%00', '/%20', '/bad%', '/%FF', '', null,
    '/' + 'a'.repeat(2048)]) assert.throws(() => routeReference(route), String(route));
});
test('frame source, document session and revision fence old intents', () => {
  const source = {}, foreign = {}, session = new FrameSession(source, '/');
  const hello = {channel:CHANNEL,type:'hello',version:1,document:'doc-1'};
  assert.equal(session.receive(foreign, hello), null);
  assert.equal(session.receive(source, {...hello, channel:'empyrean-v1'}), null);
  assert.equal(session.receive(source, hello).type, 'hello');
  const state = session.restore('/', 'initial');
  const commit = {channel:CHANNEL,type:'commit',session:state.session,baseRevision:state.revision,route:'/list',mode:'push'};
  assert.equal(session.receive(source, commit).type, 'commit');
  assert.equal(session.receive(foreign, commit), null);
  assert.equal(session.receive(source, {...commit, session:'retired'}), null);
  session.restore('/new', 'traversal');
  assert.equal(session.receive(source, commit).type, 'stale');
  assert.equal(session.receive(source, {...hello, document:'old-doc'}), null);
  assert.equal(session.receive(source, {...commit,baseRevision:session.revision,route:'//evil'}).type, 'invalid');
});
