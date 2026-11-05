// Isolated design fixture. Not imported by the production application.
export const CHANNEL = 'empyrean-navigation-v1';
const simplePath = value => /^\/[A-Za-z0-9/_-]*$/.test(value) && !value.startsWith('//');
export function routeReference(value) {
  if (typeof value !== 'string' || !value.startsWith('/') || value.startsWith('//') ||
      new TextEncoder().encode(value).length > 2048 || /[\s\\\u0000-\u001f\u007f]/u.test(value) ||
      /%(?![a-f\d]{2})/i.test(value)) throw Error('Invalid route');
  const path = value.split(/[?#]/, 1)[0];
  // Decode only once for validation; never use the decoded value as a fetch target.
  let decoded;
  try { decoded = decodeURIComponent(path); } catch { throw Error('Invalid route encoding'); }
  if (/[\\\u0000-\u0020\u007f]/u.test(decoded) || /%2f|%5c/i.test(path) ||
      decoded.split('/').some(part => part === '.' || part === '..')) throw Error('Invalid route path');
  return value;
}
export function readEnvelope(input) {
  const url = new URL(input);
  const module = /^\/app\/modules\/([a-z][a-z0-9]*(?:-[a-z0-9]+)*)$/.exec(url.pathname)?.[1];
  if (!module) return null;
  const params = url.searchParams;
  const path = params.get('path') || '/';
  if (!simplePath(path)) throw Error('Invalid bootstrap path');
  if (!params.has('nav') && !params.has('route')) return { module, path, route: path, version: 0 };
  if (['path', 'nav', 'route'].some(key => params.getAll(key).length > 1) ||
      params.get('nav') !== '1' || !params.has('route')) throw Error('Invalid navigation envelope');
  return { module, path, route: routeReference(params.get('route')), version: 1 };
}
export function writeEnvelope(input, route) {
  const url = new URL(input);
  if (!readEnvelope(url)) throw Error('Not a module URL');
  url.searchParams.set('nav', '1');
  url.searchParams.set('route', routeReference(route));
  return url.pathname + url.search + url.hash;
}
export class FrameSession {
  constructor(source, route, revision = 0) {
    this.source = source;
    this.route = route;
    this.revision = revision;
    this.session = crypto.randomUUID();
  }
  receive(source, message) {
    if (source !== this.source || !message || message.channel !== CHANNEL) return null;
    if (message.type === 'hello') {
      if (message.version !== 1 || typeof message.document !== 'string' ||
          !/^[a-zA-Z0-9-]{1,100}$/.test(message.document)) return null;
      // One document per freshly mounted fixture frame. A reload remounts the frame.
      if (this.document && this.document !== message.document) return null;
      this.document = message.document;
      return { type: 'hello' };
    }
    if (!this.document || message.session !== this.session) return null;
    if (message.type !== 'commit') return null;
    if (message.baseRevision !== this.revision) return { type: 'stale' };
    if (!['push', 'replace'].includes(message.mode)) return { type: 'invalid' };
    try { return { type: 'commit', route: routeReference(message.route), mode: message.mode }; }
    catch { return { type: 'invalid' }; }
  }
  restore(route, cause) {
    this.route = routeReference(route);
    return { channel: CHANNEL, type: 'restore', document: this.document,
      session: this.session, revision: ++this.revision, route: this.route, cause };
  }
}
