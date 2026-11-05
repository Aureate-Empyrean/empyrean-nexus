// URLs identify control-panel views; module resource identities never depend on them.
import './navigation-protocol.js';
export const routes = Object.freeze({
  overview: '/app/overview', modules: '/app/modules', activity: '/app/activity',
  settings: '/app/settings', notifications: '/app/notifications',
});
export function matchRoute(pathname, search = '') {
  if (pathname === '/' || pathname === '/app' || pathname === '/app/') return { name: 'overview' };
  for (const [name, path] of Object.entries(routes)) if (pathname === path) return { name };
  const match = /^\/app\/modules\/([a-z][a-z0-9]*(?:-[a-z0-9]+)*)$/.exec(pathname);
  if (match) {
    const path = new URLSearchParams(search).get('path') || '/';
    if (!/^\/[a-zA-Z0-9/_-]*$/.test(path) || path.startsWith('//')) return { name: 'not-found' };
    try {
      const navigationRoute = globalThis.EmpyreanNavigation.envelope(search);
      return { name: 'module', id: match[1], modulePath: path,
        ...(navigationRoute === null ? {} : {navigationRoute}) };
    } catch { return { name: 'not-found' }; }
  }
  return { name: 'not-found' };
}
export function createRouter(onNavigate) {
  const read = cause => onNavigate(matchRoute(location.pathname, location.search), {cause});
  window.addEventListener('popstate', () => read('traversal'));
  return {
    start() {
      if (['/', '/app', '/app/'].includes(location.pathname)) history.replaceState(null, '', routes.overview);
      read('initial');
    },
    navigate(path) {
      const url = new URL(path, location.origin);
      if (url.origin !== location.origin || !url.pathname.startsWith('/app/')) return;
      if (url.pathname + url.search !== location.pathname + location.search) history.pushState(null, '', url.pathname + url.search);
      read('navigate');
    },
  };
}
