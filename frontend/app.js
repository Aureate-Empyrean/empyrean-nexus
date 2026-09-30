import { enter, leave, stagger, feedback, toggleDetails } from './motion.js';
import { createRouter, routes } from './router.js';

const app = document.querySelector('#app');
const dialog = document.querySelector('#dialog');
let csrf = '', username = '', system = null, modules = [], notices = [];
let view = { name: 'overview' }, renderEpoch = 0, refreshEpoch = 0, toastTimer, dialogEpoch = 0;
let openPopover = null, toastEpoch = 0;
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const date = value => new Date(value).toLocaleString();
const title = name => name.charAt(0).toUpperCase() + name.slice(1);
const icon = name => ({ overview: '◈', modules: '▦', activity: '≡', settings: '⚙' }[name] || '◇');
const router = createRouter(route => {
  view = route;
  closePopovers();
  if (dialog.open) { dialogEpoch++; dialog.close(); }
  if (username && system) renderView({ transition: true, focus: true });
});

function toast(message, type = 'success') {
  const epoch = ++toastEpoch;
  const element = document.querySelector('#toast');
  element.textContent = message;
  element.dataset.type = type;
  element.setAttribute('role', type === 'error' ? 'alert' : 'status');
  element.hidden = false;
  enter(element);
  clearTimeout(toastTimer);
  toastTimer = setTimeout(async () => { await leave(element); if (epoch === toastEpoch) element.hidden = true; }, 6000);
}
async function api(path, options = {}) {
  const response = await fetch('/api/v1' + path, {
    ...options, headers: { 'Content-Type': 'application/json', 'X-Nexus-CSRF': csrf, ...options.headers },
  });
  const data = await response.json();
  if (!response.ok) {
    if (response.status === 401 && username) { username = ''; system = null; dialog.close(); auth(false); }
    throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail));
  }
  return data;
}
function action(label, fn, kind = '', busyLabel = 'Working…') {
  const button = document.createElement('button');
  button.textContent = label;
  button.className = kind;
  button.onclick = async () => {
    button.disabled = true;
    button.classList.add('is-busy');
    button.setAttribute('aria-busy', 'true');
    button.textContent = busyLabel;
    try { await fn(); } catch (error) { toast(error.message, 'error'); }
    finally { button.disabled = false; button.classList.remove('is-busy'); button.removeAttribute('aria-busy'); button.textContent = label; }
  };
  return button;
}
async function closeDialog() {
  const epoch = ++dialogEpoch;
  await leave(dialog);
  if (epoch === dialogEpoch) dialog.close();
}
function modal(label, content) {
  dialogEpoch++;
  const wasOpen = dialog.open;
  dialog.innerHTML = `<div class="dialog-top"><h2 id="dialog-title">${esc(label)}</h2><button class="quiet" aria-label="Close dialog">✕</button></div>${content}`;
  dialog.setAttribute('aria-labelledby', 'dialog-title');
  dialog.querySelector('button').onclick = closeDialog;
  if (!wasOpen) { closePopovers(); dialog.showModal(); }
  enter(dialog);
}
dialog.addEventListener('cancel', event => { event.preventDefault(); closeDialog(); });
dialog.addEventListener('click', event => {
  const rect = dialog.getBoundingClientRect();
  if (event.target === dialog && (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom)) closeDialog();
});
document.addEventListener('click', event => {
  const link = event.target.closest('a[data-route]');
  if (link && event.button === 0 && !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey) {
    event.preventDefault(); router.navigate(link.getAttribute('href')); return;
  }
  const summary = event.target.closest('details > summary');
  if (summary) { event.preventDefault(); toggleDetails(summary.parentElement); }
  if (openPopover && !event.target.closest('.popover, [data-popover-trigger]')) closePopovers();
});
document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && openPopover) { const trigger = openPopover.trigger; closePopovers(); trigger?.focus(); }
});
function closePopovers() {
  if (!openPopover) return;
  const { panel, trigger } = openPopover;
  openPopover = null;
  trigger?.setAttribute('aria-expanded', 'false');
  leave(panel).then(() => { if (openPopover?.panel !== panel) panel.hidden = true; });
}
function togglePopover(panel, trigger) {
  if (openPopover?.panel === panel) { closePopovers(); return; }
  closePopovers();
  panel.hidden = false;
  trigger.setAttribute('aria-expanded', 'true');
  openPopover = { panel, trigger };
  enter(panel);
  panel.querySelector('button, a')?.focus();
}
function skeleton() {
  return '<div class="skeleton-layout" aria-busy="true" aria-label="Loading view"><div class="skeleton skeleton-title"></div><div class="skeleton skeleton-block"></div><div class="skeleton skeleton-block"></div><span class="sr-only">Loading…</span></div>';
}
function auth(setup) {
  renderEpoch++;
  app.innerHTML = `<main class="auth-screen"><div class="auth-brand"><span class="brand-mark" aria-hidden="true">✧</span><div><strong>Empyrean Nexus</strong><small>Aureate Empyrean</small></div></div><section class="auth-box"><h1>${setup ? 'Set up Nexus' : 'Sign in'}</h1><form id="auth-form">${setup ? '<label for="installation">Installation name</label><input id="installation" name="installation" value="My Nexus" maxlength="80" required><label for="claim">Installation claim token</label><input id="claim" name="claim" type="password" autocomplete="off" required><p class="help">Read on the server: <code>docker compose exec nexus cat /data/setup-token</code></p>' : ''}<label for="username">Username</label><input id="username" name="username" autocomplete="username" pattern="[a-zA-Z0-9_.-]+" maxlength="80" required><label for="password">Password</label><input id="password" name="password" type="password" minlength="12" maxlength="128" autocomplete="${setup ? 'new-password' : 'current-password'}" required>${setup ? '<p class="help">At least 12 characters. This creates the local administrator account.</p>' : ''}<p class="error-text" role="alert" id="auth-error"></p><button class="primary" type="submit">${setup ? 'Create administrator' : 'Sign in'}</button></form></section></main>`;
  enter(app.querySelector('.auth-box'));
  document.querySelector('#auth-form').onsubmit = async event => {
    event.preventDefault();
    const button = event.target.querySelector('button');
    const label = button.textContent;
    button.disabled = true; button.classList.add('is-busy'); button.textContent = setup ? 'Initializing…' : 'Signing in…';
    const values = new FormData(event.target);
    const body = { username: values.get('username'), password: values.get('password') };
    if (setup) Object.assign(body, { claim_token: values.get('claim'), installation_name: values.get('installation') });
    try {
      const session = await api(setup ? '/setup' : '/auth/login', { method: 'POST', body: JSON.stringify(body) });
      csrf = session.csrf; username = session.username;
      app.innerHTML = `<main class="content">${skeleton()}</main>`;
      await refresh({ initial: true });
    } catch (error) {
      const errorEl = document.querySelector('#auth-error');
      if (errorEl) { errorEl.textContent = error.message; enter(errorEl); }
      else toast(error.message, 'error');
    } finally { button.disabled = false; button.classList.remove('is-busy'); button.textContent = label; }
  };
}
async function refresh({ initial = false, changed = null } = {}) {
  const epoch = ++refreshEpoch;
  const data = await Promise.all([api('/system'), api('/modules'), api('/notifications')]);
  if (epoch !== refreshEpoch || !username) return;
  const added = data[1].filter(m => !modules.some(old => old.id === m.id)).map(m => m.id);
  [system, modules, notices] = data;
  if (!document.querySelector('.shell')) shell();
  updateChrome();
  await renderView({ transition: initial, changed, added });
}
function hasUpdate() { return system?.update?.status === 'available' && !!system.update.version && system.update.version !== system.version; }
function updateLabel() {
  if (hasUpdate()) return `v${system.update.version} available`;
  if (system.update.status === 'current') return 'Up to date';
  return system.update.discovery_supported ? 'Not checked' : 'Discovery not configured';
}
function shell() {
  app.innerHTML = `<div class="shell"><aside class="sidebar"><button class="brand brand-switch" id="product-switch" data-popover-trigger aria-expanded="false" aria-controls="product-menu" aria-label="Switch application"><span class="brand-mark" aria-hidden="true">✧</span><span><strong id="product-name">Nexus</strong><small>Aureate Empyrean</small></span><span class="chevron" aria-hidden="true">⌄</span></button><div id="product-menu" class="popover switcher-panel" role="dialog" aria-label="Applications" hidden></div><nav class="nav" aria-label="Nexus navigation">${['overview', 'modules', 'activity'].map(name => `<a data-route href="${routes[name]}" data-nav="${name}"><span class="symbol" aria-hidden="true">${icon(name)}</span>${title(name)}</a>`).join('')}</nav><div class="sidebar-bottom"><div id="update-slot"></div><nav class="utility-nav" aria-label="Nexus utilities"><a data-route data-nav="settings" href="${routes.settings}"><span aria-hidden="true">⚙</span> Settings</a><button class="version-item" id="version-button"></button></nav></div></aside><div class="workspace"><header class="topbar"><div class="breadcrumb" id="breadcrumb"></div><div class="top-actions"><button id="bell" data-popover-trigger class="quiet notification-trigger" aria-expanded="false" aria-controls="notification-panel" aria-label="Notifications"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M9 21h6"/></svg><span id="unread-indicator" hidden></span></button><div id="notification-panel" class="popover notification-panel" role="dialog" aria-label="Notifications" hidden></div><span class="small">${esc(username)}</span><span class="avatar" aria-hidden="true">${esc(username.charAt(0).toUpperCase())}</span><button id="logout" class="quiet">Sign out</button></div></header><main class="content" id="content"></main></div></div>`;
  document.querySelector('#product-switch').onclick = event => { renderSwitcher(); togglePopover(document.querySelector('#product-menu'), event.currentTarget); };
  document.querySelector('#bell').onclick = async event => {
    renderNotificationPanel();
    togglePopover(document.querySelector('#notification-panel'), event.currentTarget);
    if (openPopover?.panel.id === 'notification-panel') {
      try { notices = await api('/notifications'); if (username && document.querySelector('.shell')) updateChrome(); }
      catch (error) { toast(error.message, 'error'); }
    }
  };
  document.querySelector('#version-button').onclick = releaseDialog;
  document.querySelector('#logout').onclick = async () => {
    try { await api('/auth/logout', { method: 'POST' }); username = ''; csrf = ''; system = null; refreshEpoch++; closePopovers(); auth(false); }
    catch (error) { toast(error.message, 'error'); }
  };
}
function updateChrome() {
  const unread = notices.filter(n => !n.read).length;
  const indicator = document.querySelector('#unread-indicator');
  indicator.hidden = !unread; indicator.textContent = unread > 99 ? '99+' : unread;
  document.querySelector('#bell').setAttribute('aria-label', `Notifications${unread ? `, ${unread} unread` : ''}`);
  document.querySelector('#version-button').innerHTML = `Nexus v${esc(system.version)}${hasUpdate() ? '<span class="update-indicator" aria-label="Update available">↗</span>' : ''}`;
  const slot = document.querySelector('#update-slot');
  slot.innerHTML = hasUpdate() ? `<button class="update-card" id="update-card"><span class="eyebrow">Nexus update</span><strong>v${esc(system.update.version)} available</strong><span>View release <span aria-hidden="true">→</span></span></button>` : '';
  document.querySelector('#update-card')?.addEventListener('click', releaseDialog);
  if (openPopover?.panel.id === 'notification-panel') renderNotificationPanel();
}
function renderSwitcher() {
  const panel = document.querySelector('#product-menu');
  panel.innerHTML = `<div class="popover-heading"><h2>Applications</h2></div><a data-route href="${routes.overview}" class="switcher-item">Nexus <small>Control panel</small></a>${modules.filter(m => m.state === 'enabled').map(m => `<a data-route class="switcher-item" href="/app/modules/${m.id}">${esc(m.manifest.name)}<small>v${esc(m.manifest.version)}</small></a>`).join('')}<a data-route class="switcher-manage" href="${routes.modules}">Manage modules →</a>`;
}
function notificationItems(items) {
  return items.length ? items.map(n => `<article class="notification ${n.read ? '' : 'unread'}"><div class="notification-meta"><span class="badge">${esc(n.source)}</span>${!n.read ? '<span class="unread-label">Unread</span>' : ''}</div><p>${esc(n.message)}</p><time class="small" datetime="${esc(n.created_at)}">${esc(date(n.created_at))}</time></article>`).join('') : '<p class="empty-compact">No notifications.</p>';
}
function renderNotificationPanel() {
  const panel = document.querySelector('#notification-panel');
  panel.innerHTML = `<div class="popover-heading"><h2>Notifications</h2><div id="panel-read-action"></div></div><div class="notification-scroll">${notificationItems(notices.slice(0, 6))}</div><a data-route class="popover-footer" href="${routes.notifications}">Notification history →</a>`;
  if (notices.some(n => !n.read)) panel.querySelector('#panel-read-action').append(action('Mark all read', markNotificationsRead, 'quiet', 'Saving…'));
}
async function markNotificationsRead() {
  await api('/notifications/read', { method: 'POST' });
  notices = await api('/notifications'); updateChrome();
  if (view.name === 'notifications') renderView();
}
function heading(label, extra = '') { return `<div class="page-heading"><h1 tabindex="-1">${esc(label)}</h1><div class="heading-actions" id="heading-action">${extra}</div></div>`; }
async function renderView({ transition = false, focus = false, changed = null, added = [] } = {}) {
  const epoch = ++renderEpoch;
  const content = document.querySelector('#content');
  if (!content) return;
  const module = view.name === 'module' ? modules.find(m => m.id === view.id) : null;
  document.body.classList.toggle('application-mode', !!(module?.state === 'enabled' && module.manifest.capabilities.includes('ui.application')));
  document.querySelectorAll('[data-nav]').forEach(link => {
    const active = link.dataset.nav === view.name;
    link.classList.toggle('active', active);
    if (active) link.setAttribute('aria-current', 'page'); else link.removeAttribute('aria-current');
  });
  document.querySelector('#product-name').textContent = module?.manifest.name || 'Nexus';
  document.querySelector('#breadcrumb').textContent = view.name === 'module' ? (module?.manifest.name || 'Module') : `${system.name} / ${title(view.name)}`;
  document.title = `${module?.manifest.name || title(view.name)} · Empyrean Nexus`;
  if (view.name === 'overview' || view.name === 'modules') renderModules(content);
  else if (view.name === 'settings') renderSettings(content);
  else if (view.name === 'activity') {
    content.innerHTML = heading('Activity') + skeleton();
    try {
      const data = await api('/activity/entries');
      if (epoch !== renderEpoch) return;
      renderActivity(content, data);
    } catch (error) { if (epoch === renderEpoch) content.innerHTML = heading('Activity') + `<p role="alert" class="error-text">${esc(error.message)}</p>`; }
  } else if (view.name === 'notifications') {
    content.innerHTML = heading('Notification history') + `<section class="panel">${notificationItems(notices)}</section>`;
    document.querySelector('#heading-action').append(action('Mark all read', markNotificationsRead, '', 'Saving…'));
  } else if (view.name === 'module') renderModuleView(content, module);
  else content.innerHTML = heading('Page not found') + `<a data-route href="${routes.overview}">Return to Overview</a>`;
  if (epoch !== renderEpoch) return;
  if (transition) { enter(content); stagger(content.querySelectorAll('.stat, .module')); }
  if (!transition && added.length) stagger(added.map(id => document.querySelector(`[data-module-id="${CSS.escape(id)}"]`)).filter(Boolean));
  if (changed && !added.includes(changed)) feedback(document.querySelector(`[data-module-id="${CSS.escape(changed)}"]`));
  if (focus) content.querySelector('h1')?.focus({ preventScroll: true });
}
function renderModules(content) {
  const enabled = modules.filter(m => m.state === 'enabled').length;
  const problems = modules.filter(m => m.state === 'error' || ['unhealthy', 'unreachable'].includes(m.health));
  content.innerHTML = heading(view.name === 'overview' ? 'Overview' : 'Modules') + (view.name === 'overview' ? `<section class="stats" aria-label="System summary"><article class="stat"><div class="stat-label">Nexus health<span class="dot"></span></div><div class="stat-value good">Operational</div><div class="stat-foot">API and database responding</div></article><article class="stat"><div class="stat-label">Modules</div><div class="stat-value">${modules.length}</div><div class="stat-foot">${enabled} enabled${problems.length ? ` · ${problems.length} need attention` : ''}</div></article><article class="stat"><div class="stat-label">Nexus version</div><div class="stat-value mono">v${esc(system.version)}</div><div class="stat-foot">${esc(updateLabel())}</div></article><article class="stat"><div class="stat-label">Available storage</div><div class="stat-value">${(system.data_free_bytes / 1073741824).toFixed(1)} <small>GiB</small></div><div class="stat-foot">Nexus data filesystem</div></article></section>` : '') + `<section class="panel"><div class="panel-heading"><h2>Installed modules</h2><span class="badge">${modules.length}</span></div><div id="module-list"></div></section>`;
  const actions = document.querySelector('#heading-action');
  actions.append(action('Refresh', () => refresh(), 'quiet', 'Refreshing…'), action('+ Install module', installDialog, 'primary'));
  const list = document.querySelector('#module-list');
  if (!modules.length) { list.innerHTML = '<div class="empty"><h3>No modules installed</h3><p>Install a module from its JSON manifest.</p></div>'; return; }
  modules.forEach(module => {
    const m = module.manifest;
    const row = document.createElement('article'); row.className = 'module'; row.dataset.moduleId = m.id;
    row.innerHTML = `<div><h3>${esc(m.name)}</h3><div class="module-meta"><span class="badge ${module.state === 'enabled' ? 'good' : module.state === 'error' ? 'error' : ''}">${esc(module.state)}</span><span class="mono muted">v${esc(m.version)}</span><span class="badge">${esc(module.provenance.status)}</span><span class="small">Last health: ${esc(module.health)}</span></div></div><div class="actions"></div>`;
    const buttons = row.querySelector('.actions');
    buttons.append(action('Inspect', () => inspectDialog(module)));
    if (module.state === 'enabled') {
      const link = document.createElement('a'); link.className = 'button-link primary'; link.href = `/app/modules/${m.id}`; link.dataset.route = ''; link.textContent = 'Open'; buttons.append(link);
      buttons.append(action('Health', () => health(module), '', 'Checking…'), action('Disable', () => lifecycle(module, 'disable'), '', 'Disabling…'));
    } else buttons.append(action('Enable', () => lifecycle(module, 'enable'), 'primary', 'Starting…'));
    buttons.append(action('Uninstall', () => uninstallDialog(module), 'danger'));
    list.append(row);
  });
}
async function health(module) {
  const result = await api(`/modules/${module.id}/health`, { method: 'POST' });
  await refresh({ changed: module.id });
  toast(`Health: ${result.status}`, ['unreachable', 'unhealthy'].includes(result.status) ? 'error' : 'success');
}
async function lifecycle(module, operation) {
  const row = document.querySelector(`[data-module-id="${CSS.escape(module.id)}"]`);
  row?.classList.add('is-pending');
  try {
    await api(`/modules/${module.id}/${operation}`, { method: 'POST' });
    await refresh({ changed: module.id });
    toast(`${module.manifest.name} ${operation === 'enable' ? 'enabled' : 'disabled'}.`);
  } catch (error) { await refresh({ changed: module.id }); throw error; }
  finally { row?.classList.remove('is-pending'); }
}
function installDialog() {
  modal('Install module', `<p>Review the manifest before granting capabilities. Installation registers the module; enabling runs its container.</p><div id="sample-action"></div><label for="manifest">JSON manifest</label><textarea id="manifest" spellcheck="false" placeholder="Paste manifest"></textarea><label for="manifest-file">Or select a file</label><input id="manifest-file" type="file" accept=".json,application/json"><p class="error-text" id="review-error" role="alert"></p><div id="review-result"></div><div class="dialog-actions" id="install-actions"></div>`);
  const context = dialogEpoch;
  const text = dialog.querySelector('#manifest'), result = dialog.querySelector('#review-result');
  if (system?.development?.reference_module) dialog.querySelector('#sample-action').append(action('Load reference manifest', async () => { text.value = JSON.stringify(await api('/example-manifest'), null, 2); result.innerHTML = ''; }, 'quiet', 'Loading…'));
  dialog.querySelector('#manifest-file').onchange = async event => {
    const file = event.target.files[0];
    if (file && file.size <= 65536) { text.value = await file.text(); result.innerHTML = ''; }
    else toast('Choose a manifest smaller than 64 KiB.', 'error');
  };
  text.oninput = () => { result.innerHTML = ''; };
  dialog.querySelector('#install-actions').append(action('Review', async () => {
    try {
      const reviewedText = text.value;
      const manifest = JSON.parse(reviewedText);
      const review = await api('/modules/validate', { method: 'POST', body: JSON.stringify(manifest) });
      if (context !== dialogEpoch || text.value !== reviewedText) return;
      result.innerHTML = `<div class="review"><h3>${esc(manifest.name)} <span class="badge">Community · unreviewed</span></h3><p>${esc(manifest.description)}</p><dl class="metadata"><dt>Publisher (self-declared)</dt><dd>${esc(manifest.publisher.name)}</dd><dt>Image</dt><dd><code>${esc(manifest.container.image)}</code></dd><dt>Internal port</dt><dd>${manifest.container.port}</dd></dl><div class="caps">${review.capabilities.map(c => `<code>${esc(c)}</code>`).join('') || 'No capabilities requested'}</div>${manifest.references ? `<h3 class="spaced">Cross-module scopes</h3><pre>${esc(JSON.stringify(manifest.references, null, 2))}</pre><p>Read scopes do not reveal private relationships. Resolution can expose owner-approved metadata.</p>` : ''}<p>${esc(review.warning)}</p>${(review.retained_references || review.retained_data) ? `<p class="warning-text">${review.retained_references} retained references${review.retained_data ? " and persistent data" : ""} use this module identity.</p><label><input type="checkbox" id="reuse-identity">Restore this identity with the same resource IDs. A different dataset could misdirect existing references.</label>` : ''}<label><input type="checkbox" id="consent">Grant the capabilities and scopes shown above.</label><div id="confirm-install"></div></div>`;
      result.querySelector('#confirm-install').append(action('Install disabled', async () => {
        if (!dialog.querySelector('#consent').checked) throw new Error('Review and grant the requested capabilities first.');
        if ((review.retained_references || review.retained_data) && !dialog.querySelector('#reuse-identity').checked) throw new Error('Confirm that you are restoring the same resource identity.');
        await api('/modules', { method: 'POST', body: JSON.stringify({ manifest, grants: review.capabilities, reuse_reference_identity: !!(review.retained_references || review.retained_data) }) });
        if (context === dialogEpoch) closeDialog(); await refresh({ changed: manifest.id }); toast('Module installed disabled.');
      }, 'primary', 'Installing…'));
      dialog.querySelector('#review-error').textContent = ''; enter(result);
    } catch (error) { result.innerHTML = ''; dialog.querySelector('#review-error').textContent = error.message; }
  }, 'primary', 'Validating…'));
}
function inspectDialog(module) {
  modal(module.manifest.name, `<dl class="metadata"><dt>State</dt><dd>${esc(module.state)}</dd><dt>Installed</dt><dd>${esc(date(module.installed_at))}</dd><dt>Source</dt><dd>${esc(module.source)}</dd><dt>Publisher verification</dt><dd>Unverified</dd><dt>Updates</dt><dd>Not checked</dd></dl>${(module.external_origins || []).length ? '<h3 class="spaced">Trusted external sites</h3><ul class="trusted-origins" id="trusted-origins"></ul>' : ''}<details><summary>Manifest and capabilities</summary><div class="details-body"><pre>${esc(JSON.stringify(module.manifest, null, 2))}</pre></div></details>`);
  const list = dialog.querySelector('#trusted-origins');
  (module.external_origins || []).forEach(origin => {
    const item = document.createElement('li');
    const name = document.createElement('code'); name.textContent = origin;
    item.append(name, action('Remove', async () => {
      const result = await api(`/modules/${module.id}/external-origins?origin=${encodeURIComponent(origin)}`, { method: 'DELETE' });
      module.external_origins = result.external_origins;
      item.remove();
      toast(`${module.manifest.name} can no longer open ${origin} without asking.`);
    }, 'quiet', 'Removing…'));
    list.append(item);
  });
}
function uninstallDialog(module) {
  const persistent = module.manifest.capabilities.includes('storage.data');
  const data = persistent
    ? 'Its persistent data volume is retained, not deleted; reinstalling the same module can reuse it after explicit confirmation.'
    : 'This module declares no persistent storage; data inside its container is not kept.';
  modal('Uninstall module?', `<p>This stops and removes the container and its network, revokes its credentials, and releases port ${module.port}. ${data} Nexus audit history, shared files and resource references are retained; references may become unresolved.</p><div class="dialog-actions" id="remove-actions"></div>`);
  const context = dialogEpoch;
  dialog.querySelector('#remove-actions').append(action('Cancel', closeDialog, 'quiet'), action('Uninstall', async () => {
    await api('/modules/' + module.id, { method: 'DELETE' }); if (context === dialogEpoch) closeDialog();
    const row = document.querySelector(`[data-module-id="${CSS.escape(module.id)}"]`);
    if (row) await leave(row);
    await refresh(); toast('Module uninstalled.');
  }, 'danger', 'Removing…'));
}
function renderModuleView(content, module) {
  if (!module) { content.innerHTML = heading('Module not installed') + `<a data-route href="${routes.modules}">Manage modules</a>`; return; }
  content.innerHTML = heading(module.manifest.name, `<a data-route class="button-link" href="${routes.modules}">Manage modules</a>`);
  if (module.state !== 'enabled') { content.insertAdjacentHTML('beforeend', `<section class="panel"><span class="badge">${esc(module.state)}</span><p class="spaced">Enable this module in Modules to open it.</p></section>`); return; }
  const path = view.modulePath || '/';
  if (module.manifest.capabilities.includes('ui.application')) {
    content.innerHTML = `<iframe id="module-application" title="${esc(module.manifest.name)}" sandbox="allow-scripts allow-downloads" src="/modules/${module.id}${esc(path)}"></iframe>`;
    return;
  }
  content.insertAdjacentHTML('beforeend', `<section class="panel module-view"><div class="panel-heading"><span class="badge">v${esc(module.manifest.version)}</span><span class="small">Sandboxed module view</span></div><iframe title="${esc(module.manifest.name)}" sandbox="allow-scripts" src="/modules/${module.id}${esc(path)}"></iframe></section><details class="panel api-explorer"><summary>Module API explorer</summary><div class="details-body"><label for="module-api-path">Path relative to ${esc(module.manifest.routes.api)}</label><input id="module-api-path" value="/info" maxlength="100"><div class="dialog-actions" id="module-api-actions"></div><pre id="module-api-result" aria-live="polite"></pre></div></details>`);
  const call = async method => {
    const input = document.querySelector('#module-api-path'), output = document.querySelector('#module-api-result');
    if (!/^\/[a-zA-Z0-9/_-]+$/.test(input.value) || input.value.startsWith('//')) throw new Error('Use a simple /api-relative path.');
    const root = module.manifest.routes.api.replace(/\/$/, '');
    const response = await fetch(`/modules/${module.id}${root}${input.value}`, { method, headers: { 'X-Nexus-CSRF': csrf, 'Content-Type': 'application/json' }, ...(method === 'POST' ? { body: '{}' } : {}) });
    const body = await response.json(); output.textContent = JSON.stringify(body, null, 2); enter(output);
    if (!response.ok) throw new Error(`Module request failed: ${response.status}`);
  };
  document.querySelector('#module-api-actions').append(action('GET', () => call('GET'), '', 'Requesting…'), action('POST', () => call('POST'), '', 'Requesting…'));
}
function renderSettings(content) {
  content.innerHTML = heading('Settings') + `<section class="panel"><h2>Installation</h2><form id="settings-form" class="setting-form"><label for="name">Installation name</label><input id="name" value="${esc(system.name)}" maxlength="80" required><label for="locale">Locale (language tag)</label><input id="locale" value="${esc(system.locale || 'en')}" maxlength="35"><div class="spaced"><button class="primary">Save</button></div></form></section><section class="panel"><h2>Metadata export</h2><p>Includes settings, manifests, references, retained events, notifications, and audit records. Credentials are excluded.</p><a class="button-link" href="/api/v1/export" download="nexus-export.json">Download JSON</a><p class="help">This is not a restorable backup. Exported metadata can contain private information.</p></section><details class="panel"><summary>Developer contracts</summary><div class="details-body"><p><a href="/api/v1/openapi.json" target="_blank" rel="noopener">OpenAPI JSON ↗</a> · <a href="/api/v1/protocol" target="_blank" rel="noopener">Module schema ↗</a></p></div></details>`;
  document.querySelector('#settings-form').onsubmit = async event => {
    event.preventDefault(); const button = event.target.querySelector('button');
    button.disabled = true; button.classList.add('is-busy'); button.textContent = 'Saving…';
    try { await api('/settings', { method: 'PATCH', body: JSON.stringify({ installation_name: document.querySelector('#name').value, locale: document.querySelector('#locale').value }) }); await refresh(); toast('Settings saved.'); }
    catch (error) { toast(error.message, 'error'); }
    finally { button.disabled = false; button.classList.remove('is-busy'); button.textContent = 'Save'; }
  };
}
function activityText(item) {
  const action = item.kind;
  const names = { 'setup.completed': 'Installation initialized', 'auth.login': 'Owner signed in', 'settings.changed': 'Settings changed', 'metadata.exported': 'Metadata exported' };
  if (names[action]) return names[action];
  if (action.startsWith('module.')) {
    const pieces = action.split('.');
    const verbs = { enable: 'Enable', disable: 'Disable', uninstall: 'Uninstall', installed: 'Installed', health: 'Health', compatibility: 'Compatibility', update: 'Update', backup: 'Backup', restore: 'Restore', references: 'References' };
    return `${verbs[pieces[1]] || pieces[1]}${pieces[2] ? ` · ${pieces[2]}` : ''}`;
  }
  return action;
}
function renderActivity(content, data) {
  content.innerHTML = heading('Activity') + '<section class="panel activity-list" id="activity-list"></section><div id="activity-more"></div>';
  document.querySelector('#heading-action').append(action('Refresh', () => renderView(), 'quiet', 'Refreshing…'));
  const append = items => {
    const list = document.querySelector('#activity-list');
    if (!items.length && !list.children.length) list.innerHTML = '<p class="empty-compact">No activity recorded.</p>';
    items.forEach(item => {
      const row = document.createElement('article'); row.className = 'activity-row';
      row.innerHTML = `<span class="activity-marker ${item.kind.endsWith('.failed') ? 'failed' : ''}" aria-hidden="true"></span><div><h3>${esc(activityText(item))}</h3><span class="small">${esc(item.subject)} · ${esc(item.actor)}</span></div><time class="small" datetime="${esc(item.occurred_at)}">${esc(date(item.occurred_at))}</time>`;
      list.append(row);
    });
  };
  append(data.items);
  let cursor = data.next_cursor;
  if (data.has_more) {
    const button = action('Load earlier activity', async () => {
      const epoch = renderEpoch;
      const page = await api('/activity/entries?before=' + cursor);
      if (epoch !== renderEpoch) return;
      append(page.items); cursor = page.next_cursor;
      if (!page.has_more) button.remove();
    }, '', 'Loading…');
    document.querySelector('#activity-more').append(button);
  }
}
function safeReleaseURL(value) { try { const url = new URL(value); return url.protocol === 'https:' && !url.username && !url.password ? url.href : null; } catch { return null; } }
function releaseDialog() {
  const update = system.update, release = hasUpdate() ? update : (system.release || {});
  const source = safeReleaseURL(release.url);
  modal('Nexus release', `<dl class="metadata"><dt>Installed version</dt><dd>v${esc(system.version)}</dd><dt>Update status</dt><dd>${esc(updateLabel())}</dd>${hasUpdate() ? `<dt>Available version</dt><dd>v${esc(update.version)}</dd>` : ''}${release.published_at ? `<dt>Release date</dt><dd>${esc(date(release.published_at))}</dd>` : ''}${source ? `<dt>Release source</dt><dd><a href="${esc(source)}" target="_blank" rel="noopener noreferrer">${esc(new URL(source).hostname)} ↗</a></dd>` : ''}</dl>${release.notes ? `<h3>Release notes</h3><pre>${esc(release.notes)}</pre>` : ''}<p class="help">${system.update.discovery_supported ? 'Opening release information does not install an update.' : 'Update discovery is not configured. Nexus has not checked for a newer release.'}</p>${hasUpdate() ? '<p class="help">Automatic installation is not implemented. Review the deployment instructions before updating.</p>' : ''}`);
}

router.start();
(async () => {
  try {
    const setup = await api('/setup');
    if (setup.required) { auth(true); return; }
    try { const session = await api('/auth/session'); csrf = session.csrf; username = session.username; }
    catch { auth(false); return; }
    await refresh({ initial: true });
  } catch (error) {
    app.innerHTML = `<main class="loading"><h1>Nexus unavailable</h1><p>${esc(error.message)}</p><button id="retry">Retry</button></main>`;
    document.querySelector('#retry').onclick = () => location.reload();
  }
})();

// External navigation is a data channel: whatever a module puts in a URL reaches its destination.
// Trust is therefore granted to an ORIGIN for ONE module, in Nexus's own dialog, and granting it
// sends nothing: the requested URL is not opened. Only later requests to an origin the owner already
// trusted for that module open directly. mailto never carries module-supplied subject/body/headers.
// Buttons arm after a short delay so a dialog raised under the pointer cannot capture a click.
const EXTERNAL_ARM_MS = 600;
const MAIL_ADDRESS = /^[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$/;
function externalTarget(value) {
  if (typeof value !== 'string' || value.length > 2048) throw Error('Unsupported external link');
  const url = new URL(value);
  if (!['https:', 'http:', 'mailto:'].includes(url.protocol) || url.username || url.password) throw Error('Unsupported external link');
  return url;
}
function mailRecipient(url) {
  let address = '';
  try { address = decodeURIComponent(url.pathname); } catch { /* rejected below */ }
  if (address.length > 254 || !MAIL_ADDRESS.test(address)) throw Error('Unsupported email address');
  return address;
}
function decide(label, content, confirmLabel, confirm) {
  return new Promise(resolve => {
    modal(label, `${content}<div class="dialog-actions" id="external-actions"></div>`);
    const epoch = dialogEpoch;
    let settled = false;
    const done = value => { if (!settled) { settled = true; clearInterval(watch); resolve(value); } };
    // Closing or replacing the dialog by any other means is a refusal.
    const watch = setInterval(() => { if (epoch !== dialogEpoch || !dialog.open) done(false); }, 150);
    const cancel = action('Cancel', () => { done(false); return closeDialog(); }, 'quiet');
    const accept = action(confirmLabel, async () => {
      if (settled) return;
      await confirm();
      done(true);
      return closeDialog();
    }, 'primary');
    accept.disabled = true;
    setTimeout(() => { if (!settled) accept.disabled = false; }, EXTERNAL_ARM_MS);
    dialog.querySelector('#external-actions').append(cancel, accept);
  });
}
function trustOrigin(module, url) {
  const port = url.port || (url.protocol === 'https:' ? '443' : '80') + ' (default)';
  return decide('Trust external site?', `<p>${esc(module.manifest.name)} wants to open links to this site. If you trust it, this module can open any address on it later without asking again.</p><dl class="metadata"><dt>Requested by</dt><dd>${esc(module.manifest.name)} <span class="mono muted">${esc(module.id)}</span></dd><dt>Site</dt><dd><strong id="external-origin">${esc(url.origin)}</strong></dd><dt>Scheme</dt><dd>${esc(url.protocol.slice(0, -1))}${url.protocol === 'http:' ? ' · not encrypted' : ''}</dd><dt>Host</dt><dd>${esc(url.hostname)}</dd><dt>Port</dt><dd>${esc(port)}</dd></dl><p class="help">The link it asked for is not opened now, so its path and data are not sent. Other modules are not affected. You can remove this trust in the module's details.</p>`, 'Trust this site', async () => {
    const result = await api(`/modules/${module.id}/external-origins`, { method: 'POST', body: JSON.stringify({ origin: url.origin }) });
    module.external_origins = result.external_origins;
    toast(`Trusted ${url.origin} for ${module.manifest.name}. Open the link again to continue.`);
  });
}
function composeMail(module, url, address) {
  const discarded = url.search || url.hash;
  return decide('Start an email?', `<p>${esc(module.manifest.name)} wants to start an email in your mail app.</p><dl class="metadata"><dt>To</dt><dd><strong id="external-origin">${esc(address)}</strong></dd></dl>${discarded ? '<p class="warning-text">Subject, body and other fields supplied by the module are discarded.</p>' : ''}<p class="help">Nothing is sent until you send it from your mail app.</p>`, 'Start email', () => {
    window.open('mailto:' + address, '_blank', 'noopener,noreferrer');
  });
}

// The opaque-origin application can request only its own declared API, never owner APIs.
window.addEventListener('message', async event => {
  const frame = document.querySelector('#module-application');
  const message = event.data;
  if (!frame || event.source !== frame.contentWindow || !message || message.channel !== 'empyrean-v1' || typeof message.id !== 'string' || message.id.length > 100) return;
  const module = modules.find(m => m.id === view.id);
  if (!module || module.state !== 'enabled' || !module.manifest.capabilities.includes('ui.application')) return;
  const reply = (result, error) => { if (frame.isConnected) event.source.postMessage({channel:'empyrean-v1', id:message.id, result, error}, '*'); };
  try {
    if (message.action === 'context') return reply({applications:modules.filter(m=>m.state==='enabled').map(m=>({id:m.id,name:m.manifest.name})),locale:system.locale || navigator.language});
    if (message.action === 'navigate') {
      const target=message.module;
      if (target !== 'nexus' && !modules.some(m=>m.id===target && m.state==='enabled')) throw Error('Unknown application');
      router.navigate(target==='nexus' ? routes.overview : '/app/modules/'+target);
      return;
    }
    if (message.action === 'external') {
      const url = externalTarget(message.url);
      if (url.protocol === 'mailto:') {
        const address = mailRecipient(url);
        if (dialog.open) throw Error('Nexus is waiting for another decision');
        if (!await composeMail(module, url, address)) throw Error('The email was not started');
        return reply({opened:true});
      }
      if ((module.external_origins || []).includes(url.origin)) {
        window.open(url.href, '_blank', 'noopener,noreferrer');
        return reply({opened:true});
      }
      if (dialog.open) throw Error('Nexus is waiting for another decision');
      if (!await trustOrigin(module, url)) throw Error('The site was not trusted');
      return reply({opened:false, trusted:true});
    }
    if (message.action !== 'request') throw Error('Unsupported bridge action');
    const path=message.path, method=message.method || 'GET';
    const prefix=module.manifest.routes.api.replace(/\/$/,'');
    if (typeof path !== 'string' || !path.startsWith(prefix+'/') || !/^\/[a-zA-Z0-9/_-]+(?:\?[^#]*)?$/.test(path) || path.includes('..') || /[%\\]/.test(path.split('?')[0]) || !['GET','POST','PUT','DELETE','PATCH'].includes(method)) throw Error('Invalid module API request');
    const body=message.body === undefined ? undefined : JSON.stringify(message.body);
    if (body && body.length > 2*1024*1024) throw Error('Request too large');
    const response=await fetch('/modules/'+module.id+path,{method,headers:{'Content-Type':'application/json','X-Nexus-CSRF':csrf},body});
    const data=await response.json();
    if (!response.ok) throw Error(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail));
    reply(data);
  } catch(error) { reply(null,error.message); }
});
