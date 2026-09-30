import { animate, enter, leave, slideIn, stagger, feedback, collapse, toggleDetails } from './motion.js';
import { createRouter, routes } from './router.js';

const app = document.querySelector('#app');
const dialog = document.querySelector('#dialog');
let csrf = '', username = '', system = null, modules = [], notices = [];
let view = { name: 'overview' }, renderEpoch = 0, refreshEpoch = 0, toastTimer, dialogEpoch = 0;
let openPopover = null, toastEpoch = 0, drawerId = null, showCodes = false;
const pendingOps = new Map();

/* ─────────────── Small helpers ─────────────── */

const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const locale = () => { try { return Intl.getCanonicalLocales(system?.locale || navigator.language || 'en')[0]; } catch { return 'en'; } };
function date(value) {
  try { return new Intl.DateTimeFormat(locale(), { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)); }
  catch { return new Date(value).toLocaleString(); }
}
function relative(value) {
  const seconds = (new Date(value).getTime() - Date.now()) / 1000;
  const abs = Math.abs(seconds);
  let format;
  try { format = new Intl.RelativeTimeFormat(locale(), { numeric: 'auto' }); } catch { format = new Intl.RelativeTimeFormat('en', { numeric: 'auto' }); }
  if (!Number.isFinite(seconds)) return '';
  if (abs < 45) return 'just now';
  if (abs < 3600) return format.format(Math.round(seconds / 60), 'minute');
  if (abs < 86400) return format.format(Math.round(seconds / 3600), 'hour');
  if (abs < 86400 * 7) return format.format(Math.round(seconds / 86400), 'day');
  return date(value);
}
function dayLabel(value) {
  const d = new Date(value), today = new Date();
  const key = x => `${x.getFullYear()}-${x.getMonth()}-${x.getDate()}`;
  const yesterday = new Date(today.getTime() - 86400000);
  if (key(d) === key(today)) return 'Today';
  if (key(d) === key(yesterday)) return 'Yesterday';
  try { return new Intl.DateTimeFormat(locale(), { weekday: 'long', day: 'numeric', month: 'long' }).format(d); } catch { return d.toDateString(); }
}
function clock(value) {
  try { return new Intl.DateTimeFormat(locale(), { timeStyle: 'short' }).format(new Date(value)); } catch { return ''; }
}
const bytes = value => {
  if (!Number.isFinite(value)) return '—';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let n = value, i = 0;
  while (n >= 1000 && i < units.length - 1) { n /= 1000; i++; }
  return `${n.toFixed(n >= 100 || i === 0 ? 0 : 1)} ${units[i]}`;
};
const plural = (n, one, other) => `${n} ${n === 1 ? one : other}`;
function versionAtLeast(version, minimum) {
  const a = String(version || '0').split(/[.+-]/).map(n => parseInt(n, 10) || 0), b = minimum.split('.').map(Number);
  for (let i = 0; i < 3; i++) if (a[i] !== b[i]) return a[i] > b[i];
  return true;
}
// Recovery, in-place updates and trusted-site management exist from Nexus 0.1.3.
const supports = () => ({ recovery: versionAtLeast(system?.version, '0.1.3'), trust: versionAtLeast(system?.version, '0.1.3') });
const moduleName = id => modules.find(m => m.id === id)?.manifest.name || id;

const ICONS = {
  overview: '<circle cx="10" cy="10" r="6.75"/><path d="M10 3.25v2M10 14.75v2M3.25 10h2M14.75 10h2"/><circle cx="10" cy="10" r="2"/>',
  modules: '<rect x="3.25" y="3.25" width="5.5" height="5.5" rx="1.4"/><rect x="11.25" y="3.25" width="5.5" height="5.5" rx="1.4"/><rect x="3.25" y="11.25" width="5.5" height="5.5" rx="1.4"/><rect x="11.25" y="11.25" width="5.5" height="5.5" rx="1.4"/>',
  activity: '<path d="M2.75 10h3.5l2-5 3.5 10 2-5h3.5"/>',
  settings: '<g transform="scale(.8333)"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></g>',
  bell: '<path d="M14.5 8.25a4.5 4.5 0 0 0-9 0c0 5-2.25 5.5-2.25 6.75h13.5c0-1.25-2.25-1.75-2.25-6.75M8.25 17.25h3.5"/>',
  chevron: '<path d="m6.5 8 3.5 3.5L13.5 8"/>',
  chevronRight: '<path d="m8 5.5 4.5 4.5L8 14.5"/>',
  more: '<circle cx="4.75" cy="10" r="1.2" fill="currentColor" stroke="none"/><circle cx="10" cy="10" r="1.2" fill="currentColor" stroke="none"/><circle cx="15.25" cy="10" r="1.2" fill="currentColor" stroke="none"/>',
  close: '<path d="m5.5 5.5 9 9M14.5 5.5l-9 9"/>',
  plus: '<path d="M10 4.5v11M4.5 10h11"/>',
  refresh: '<path d="M16 10a6 6 0 1 1-1.76-4.24M16.25 3.5v3.75H12.5"/>',
  play: '<path d="M7 4.75v10.5l8.25-5.25z"/>',
  stop: '<rect x="5.5" y="5.5" width="9" height="9" rx="1.5"/>',
  pulse: '<path d="M10 16.5s-6.25-3.6-6.25-8.1A3.4 3.4 0 0 1 10 6.3a3.4 3.4 0 0 1 6.25 2.1c0 4.5-6.25 8.1-6.25 8.1z"/>',
  arrow: '<path d="M4 10h12M11 5l5 5-5 5"/>',
  open: '<path d="M8 4.5H5.25a.75.75 0 0 0-.75.75v9.5c0 .41.34.75.75.75h9.5c.41 0 .75-.34.75-.75V12M11 4.5h4.5V9M15.25 4.75 9 11"/>',
  shield: '<path d="M10 2.75 16 5v4.75c0 3.75-2.6 6.4-6 7.5-3.4-1.1-6-3.75-6-7.5V5z"/>',
  database: '<ellipse cx="10" cy="5.25" rx="6" ry="2.25"/><path d="M4 5.25v9.5c0 1.25 2.7 2.25 6 2.25s6-1 6-2.25v-9.5M4 10c0 1.25 2.7 2.25 6 2.25s6-1 6-2.25"/>',
  link: '<path d="M8.5 11.5a3 3 0 0 0 4.25 0l2.5-2.5a3 3 0 0 0-4.25-4.25l-1 1"/><path d="M11.5 8.5a3 3 0 0 0-4.25 0l-2.5 2.5a3 3 0 0 0 4.25 4.25l1-1"/>',
  window: '<rect x="2.75" y="4" width="14.5" height="12" rx="1.75"/><path d="M2.75 7.5h14.5"/>',
  file: '<path d="M5.5 2.75h6L15.25 6.5v10a.75.75 0 0 1-.75.75h-9a.75.75 0 0 1-.75-.75V3.5a.75.75 0 0 1 .75-.75z"/><path d="M11.25 3v3.5h3.75"/>',
  signal: '<path d="M3 13.5a9.5 9.5 0 0 1 14 0M5.75 15.75a5.5 5.5 0 0 1 8.5 0"/><circle cx="10" cy="17" r=".9" fill="currentColor"/>',
  message: '<path d="M3.25 5.25h13.5v8.5H8l-3.75 2.75v-2.75h-1z"/>',
  download: '<path d="M10 3.5v9M6 9l4 4 4-4M4 16.5h12"/>',
  history: '<path d="M3.5 10a6.5 6.5 0 1 0 1.9-4.6M3.25 3.5v3.25H6.5"/><path d="M10 6.75V10l2.25 1.5"/>',
  upgrade: '<path d="M10 16V4.5M5.5 9 10 4.5 14.5 9"/>',
  globe: '<circle cx="10" cy="10" r="7"/><path d="M3 10h14M10 3c2 2 2.9 4.4 2.9 7S12 15 10 17c-2-2-2.9-4.4-2.9-7S8 5 10 3z"/>',
  trash: '<path d="M3.5 5.5h13M8 5.5V3.75h4V5.5M5 5.5l.75 11a1 1 0 0 0 1 .9h6.5a1 1 0 0 0 1-.9l.75-11"/>',
  user: '<circle cx="10" cy="7" r="3.25"/><path d="M3.75 17c.8-3 3.3-4.75 6.25-4.75s5.45 1.75 6.25 4.75"/>',
  signout: '<path d="M8 4.5H4.75v11H8M12.5 6.5 16 10l-3.5 3.5M16 10H8"/>',
  check: '<path d="m4.75 10.5 3.25 3.25 7.25-7.5"/>',
  alert: '<path d="M10 3.25 17.5 16.5h-15z"/><path d="M10 8.25v3.5M10 14.25v.01"/>',
  info: '<circle cx="10" cy="10" r="7"/><path d="M10 9v4.5M10 6.6v.01"/>',
  spark: '<path d="M10 3c.4 3.3 1.7 4.6 5 5-3.3.4-4.6 1.7-5 5-.4-3.3-1.7-4.6-5-5 3.3-.4 4.6-1.7 5-5z"/>',
  key: '<circle cx="7" cy="12.75" r="3.25"/><path d="M9.3 10.45 16 3.75M13.5 6.25l2 2M11.75 8l1.5 1.5"/>',
};
const icon = (name, cls = '') => `<svg class="i ${cls}" viewBox="0 0 20 20" aria-hidden="true" focusable="false">${ICONS[name] || ''}</svg>`;
// The Nexus mark: a star held in a ring of connected points — the platform that joins applications.
const MARK = '<svg class="nexus-mark" viewBox="0 0 32 32" aria-hidden="true" focusable="false"><circle class="mark-orbit" cx="16" cy="16" r="11.5"/><path class="mark-star" d="M16 8.5c.55 4.5 2.45 6.4 7 7-4.55.6-6.45 2.5-7 7-.55-4.5-2.45-6.4-7-7 4.55-.6 6.45-2.5 7-7z"/><circle class="mark-node" cx="16" cy="4.5" r="1.6"/><circle class="mark-node" cx="26" cy="21.75" r="1.6"/><circle class="mark-node" cx="6" cy="21.75" r="1.6"/></svg>';

/* ─────────────── Module presentation ─────────────── */

function status(module) {
  const s = module.state, h = module.health, pending = pendingOps.get(module.id);
  if (pending) return { label: pending, tone: 'pending' };
  if (s === 'enabling') return { label: 'Starting…', tone: 'pending' };
  if (s === 'disabling') return { label: 'Stopping…', tone: 'pending' };
  if (s === 'removing') return { label: 'Removing…', tone: 'pending' };
  if (s === 'restoring') return { label: 'Restoring…', tone: 'pending' };
  if (s === 'updating') return { label: 'Updating…', tone: 'pending' };
  if (s === 'error' && h === 'incompatible') return { label: 'Incompatible', tone: 'bad', attention: true, hint: 'This version does not support the running Nexus. Stop it and install a compatible release.' };
  if (s === 'error') return { label: h === 'restore_failed' ? 'Restore failed' : 'Needs attention', tone: 'bad', attention: true, hint: 'The last lifecycle operation did not finish. Retry it, or stop the module to clean up.' };
  if (s === 'disabled') return { label: 'Stopped', tone: 'idle', hint: 'Not running. Its data is kept.' };
  if (s === 'enabled') {
    if (h === 'healthy') return { label: 'Running', tone: 'good' };
    if (h === 'unhealthy') return { label: 'Unhealthy', tone: 'bad', attention: true, hint: 'The module answered its health check with an error.' };
    if (h === 'unreachable') return { label: 'Not responding', tone: 'bad', attention: true, hint: 'The module did not answer its health check.' };
    if (h === 'not_verified') return { label: 'Running', tone: 'neutral', hint: 'Health not verified since the last update.' };
    return { label: 'Running', tone: 'neutral', hint: 'Health not checked yet.' };
  }
  return { label: s, tone: 'idle' };
}
const isApplication = m => m.manifest.capabilities.includes('ui.application');
const canOpen = m => m.state === 'enabled';
function monogram(m, size = '') {
  const letter = [...(m.manifest.name || m.id).trim()][0]?.toUpperCase() || '?';
  return `<span class="monogram ${size}" aria-hidden="true">${esc(letter)}</span>`;
}
function statusPill(m) {
  const s = status(m);
  return `<span class="status tone-${s.tone}"><span class="status-dot"></span>${esc(s.label)}</span>`;
}
const CAPABILITIES = {
  'ui.application': ['window', 'Opens as a full application', 'Runs in its own isolated window inside Nexus, without access to Nexus or other applications.'],
  'storage.data': ['database', 'Keeps its own data on this server', 'A private volume that survives stopping, updating and uninstalling.'],
  'blobs.write': ['file', 'Stores files in shared storage', 'Uploaded files are kept by Nexus; the module gets access only to what it stored.'],
  'blobs.read': ['file', 'Reads files it stored', 'Knowing a file’s fingerprint is not enough; access is limited to its own files.'],
  'events.publish': ['signal', 'Announces changes', 'Publishes the event types listed below so other modules can react.'],
  'events.subscribe': ['signal', 'Listens for events', 'Receives only the exact event types listed below.'],
  'notifications.publish': ['message', 'Sends you notifications', 'Plain text only, marked with the module’s name.'],
  'references.create': ['link', 'Links its items to other items', 'Relationships stay private to this module unless it shares them explicitly.'],
  'references.read': ['link', 'Sees relationships shared with it', 'Only links it created or that were explicitly shared with it.'],
  'references.resolve': ['key', 'Looks up item titles in other modules', 'Only within the scopes below, and only what the owning module agrees to reveal.'],
};
function capabilityRows(list, { tone = '' } = {}) {
  if (!list.length) return '<p class="quiet-text">No permissions requested.</p>';
  return `<ul class="permissions">${list.map(code => {
    const [glyph, title, text] = CAPABILITIES[code] || ['shield', code, 'A capability this version of Nexus describes only by name.'];
    return `<li class="permission ${tone}">${icon(glyph)}<div><strong>${esc(title)}</strong><span>${esc(text)}</span><code>${esc(code)}</code></div></li>`;
  }).join('')}</ul>`;
}
function scopeText(scope) {
  return `${esc(moduleName(scope.module))} <span class="quiet-text">· ${esc(scope.type)}</span>`;
}

/* ─────────────── Router, feedback, dialogs, popovers ─────────────── */

const router = createRouter(route => {
  const previous = view;
  view = route;
  closePopovers();
  if (drawerId && route.name !== 'modules') closeDrawer(false);
  if (dialog.open) { dialogEpoch++; dialog.close(); }
  if (username && system) renderView({ transition: true, focus: true, from: previous });
});

function toast(message, type = 'success') {
  const epoch = ++toastEpoch;
  const element = document.querySelector('#toast');
  element.innerHTML = `${icon(type === 'error' ? 'alert' : 'check')}<span>${esc(message)}</span>`;
  element.dataset.type = type;
  element.setAttribute('role', type === 'error' ? 'alert' : 'status');
  element.hidden = false;
  enter(element);
  clearTimeout(toastTimer);
  toastTimer = setTimeout(async () => { await leave(element); if (epoch === toastEpoch) element.hidden = true; }, type === 'error' ? 8000 : 5000);
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
  button.type = 'button';
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
function modal(label, content, { wide = false } = {}) {
  dialogEpoch++;
  const wasOpen = dialog.open;
  dialog.className = wide ? 'wide' : '';
  dialog.innerHTML = `<div class="dialog-top"><h2 id="dialog-title">${esc(label)}</h2><button type="button" class="icon-button" aria-label="Close dialog">${icon('close')}</button></div><div class="dialog-body">${content}</div>`;
  dialog.setAttribute('aria-labelledby', 'dialog-title');
  dialog.querySelector('button').onclick = closeDialog;
  if (!wasOpen) { closePopovers(); dialog.showModal(); }
  animate(dialog, [{ opacity: 0, transform: 'translateY(8px) scale(.98)' }, { opacity: 1, transform: 'none' }]);
}
dialog.addEventListener('cancel', event => { event.preventDefault(); closeDialog(); });
dialog.addEventListener('click', event => {
  const rect = dialog.getBoundingClientRect();
  if (event.target === dialog && (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom)) closeDialog();
});
function confirmDialog(title, body, confirmLabel, run, kind = 'danger') {
  modal(title, `${body}<div class="dialog-actions" id="confirm-actions"></div>`);
  const context = dialogEpoch;
  dialog.querySelector('#confirm-actions').append(action('Cancel', closeDialog, 'quiet'), action(confirmLabel, async () => {
    await run();
    if (context === dialogEpoch) await closeDialog();
  }, kind, 'Working…'));
  dialog.querySelector(`#confirm-actions button.${kind}`)?.focus();
}

document.addEventListener('click', event => {
  const link = event.target.closest('a[data-route]');
  if (link && event.button === 0 && !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey) {
    event.preventDefault(); router.navigate(link.getAttribute('href')); return;
  }
  const summary = event.target.closest('details > summary');
  if (summary) { event.preventDefault(); toggleDetails(summary.parentElement); }
  if (openPopover && !event.target.closest('.popover, [data-popover-trigger]')) closePopovers();
  const row = event.target.closest('[data-module-id].module-row');
  if (row && !event.target.closest('button, a, input')) openDrawer(row.dataset.moduleId);
});
document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && openPopover) { const trigger = openPopover.trigger; closePopovers(); trigger?.focus(); return; }
  if (event.key === 'Escape' && drawerId && !dialog.open) { event.preventDefault(); closeDrawer(true); return; }
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k' && document.querySelector('#product-switch')) {
    event.preventDefault();
    document.querySelector('#product-switch').click();
    return;
  }
  const row = event.target.closest?.('.module-row');
  if (row && event.target === row) {
    const rows = [...document.querySelectorAll('.module-row')];
    const index = rows.indexOf(row);
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      rows[event.key === 'ArrowDown' ? Math.min(index + 1, rows.length - 1) : Math.max(index - 1, 0)]?.focus();
    } else if (event.key === 'Enter') {
      event.preventDefault(); openDrawer(row.dataset.moduleId);
    }
  }
  const item = event.target.closest?.('.menu-item, .launcher-item');
  if (item && (event.key === 'ArrowDown' || event.key === 'ArrowUp')) {
    const items = [...item.closest('.popover').querySelectorAll('.menu-item:not(:disabled), .launcher-item')];
    const index = items.indexOf(item);
    event.preventDefault();
    items[(index + (event.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length]?.focus();
  }
});
function closePopovers() {
  if (!openPopover) return;
  const { panel, trigger, transient } = openPopover;
  openPopover = null;
  trigger?.setAttribute('aria-expanded', 'false');
  leave(panel).then(() => {
    if (openPopover?.panel === panel) return;
    if (transient) panel.remove(); else panel.hidden = true;
  });
}
function togglePopover(panel, trigger) {
  if (openPopover?.panel === panel) { closePopovers(); return; }
  closePopovers();
  panel.hidden = false;
  trigger.setAttribute('aria-expanded', 'true');
  openPopover = { panel, trigger };
  animate(panel, [{ opacity: 0, transform: 'translateY(-4px) scale(.98)' }, { opacity: 1, transform: 'none' }], { duration: 140 });
  panel.querySelector('button, a')?.focus();
}
/** Floating menu for contextual and rare actions. items: {label, icon, run, danger, disabled, separator} */
function menu(trigger, items) {
  if (openPopover?.trigger === trigger) { closePopovers(); return; }
  closePopovers();
  const panel = document.createElement('div');
  panel.className = 'popover menu';
  panel.setAttribute('role', 'menu');
  panel.innerHTML = items.map((item, i) => item.separator ? '<div class="menu-sep" role="separator"></div>'
    : `<button type="button" role="menuitem" class="menu-item${item.danger ? ' danger' : ''}" data-index="${i}" ${item.disabled ? 'disabled' : ''}>${icon(item.icon || 'arrow')}<span>${esc(item.label)}</span></button>`).join('');
  document.body.append(panel);
  const rect = trigger.getBoundingClientRect();
  const width = panel.offsetWidth || 220, height = panel.offsetHeight || 200;
  const top = rect.bottom + 6 + height > window.innerHeight - 8 ? Math.max(8, rect.top - height - 6) : rect.bottom + 6;
  panel.style.top = `${top}px`;
  panel.style.left = `${Math.max(8, Math.min(rect.right - width, window.innerWidth - width - 8))}px`;
  trigger.setAttribute('aria-expanded', 'true');
  openPopover = { panel, trigger, transient: true };
  animate(panel, [{ opacity: 0, transform: 'translateY(-4px) scale(.98)' }, { opacity: 1, transform: 'none' }], { duration: 140 });
  panel.addEventListener('click', async event => {
    const button = event.target.closest('.menu-item');
    if (!button) return;
    const item = items[+button.dataset.index];
    closePopovers();
    try { await item.run(); } catch (error) { toast(error.message, 'error'); }
  });
  panel.querySelector('.menu-item:not(:disabled)')?.focus();
}
function skeleton() {
  return '<div class="skeleton-layout" aria-busy="true" aria-label="Loading view"><div class="skeleton skeleton-title"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line short"></div><span class="sr-only">Loading…</span></div>';
}

/* ─────────────── Sign-in and first run ─────────────── */

function auth(setup) {
  renderEpoch++;
  document.body.classList.remove('application-mode');
  app.innerHTML = `<main class="auth-screen"><div class="auth-poster">${MARK}<div class="display poster">EMPYREAN NEXUS</div><div class="display poster-sub">AUREATE EMPYREAN</div></div><section class="auth-box"><h1>${setup ? 'Set up this installation' : 'Welcome back'}</h1><p class="auth-lede">${setup ? 'Claim this Nexus and create the administrator account. Nothing leaves this server.' : 'Sign in to your control center.'}</p><form id="auth-form">${setup ? '<label for="installation">Installation name</label><input id="installation" name="installation" value="My Nexus" maxlength="80" required><label for="claim">Installation claim token</label><input id="claim" name="claim" type="password" autocomplete="off" required><p class="help">Read it on the server: <code>docker compose exec nexus cat /data/setup-token</code></p>' : ''}<label for="username">Username</label><input id="username" name="username" autocomplete="username" pattern="[a-zA-Z0-9_.\\-]+" maxlength="80" required><label for="password">Password</label><input id="password" name="password" type="password" minlength="12" maxlength="128" autocomplete="${setup ? 'new-password' : 'current-password'}" required>${setup ? '<p class="help">At least 12 characters. This creates the local administrator account.</p>' : ''}<p class="error-text" role="alert" id="auth-error"></p><button class="primary" type="submit">${setup ? 'Create administrator' : 'Sign in'}</button></form></section></main>`;
  enter(app.querySelector('.auth-box'));
  app.querySelector('#username')?.focus();
  document.querySelector('#auth-form').onsubmit = async event => {
    event.preventDefault();
    const button = event.target.querySelector('button');
    const label = button.textContent;
    button.disabled = true; button.classList.add('is-busy'); button.textContent = setup ? 'Setting up…' : 'Signing in…';
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

/* ─────────────── Data and chrome ─────────────── */

async function refresh({ initial = false, changed = null } = {}) {
  const epoch = ++refreshEpoch;
  const data = await Promise.all([api('/system'), api('/modules'), api('/notifications')]);
  if (epoch !== refreshEpoch || !username) return;
  const added = data[1].filter(m => !modules.some(old => old.id === m.id)).map(m => m.id);
  [system, modules, notices] = data;
  if (!document.querySelector('.shell')) shell();
  updateChrome();
  await renderView({ transition: initial, changed, added });
  if (drawerId) {
    if (modules.some(m => m.id === drawerId)) renderDrawer();
    else closeDrawer(false);
  }
}
function hasUpdate() { return system?.update?.status === 'available' && !!system.update.version && system.update.version !== system.version; }
function updateLabel() {
  if (hasUpdate()) return `Version ${system.update.version} is available`;
  if (system.update.status === 'current') return 'Up to date';
  return system.update.discovery_supported ? 'Not checked yet' : 'Update discovery is not configured';
}
function shell() {
  app.innerHTML = `<div class="shell"><header class="masthead" id="masthead"><div class="mast-left"><button type="button" class="product-switch" id="product-switch" data-popover-trigger aria-expanded="false" aria-controls="product-menu" aria-label="Switch application">${MARK}<span class="product-text"><span class="display wordmark">EMPYREAN NEXUS</span><span class="product-current" id="product-name">Nexus</span></span>${icon('chevron', 'chevron')}</button><div id="product-menu" class="popover launcher" role="dialog" aria-label="Applications" hidden><div class="launcher-head"><span>Applications</span><kbd>Ctrl K</kbd></div><div id="launcher-items"></div><button type="button" class="launcher-version" id="version-button"></button></div><nav class="nav" aria-label="Nexus navigation"><span class="nav-ink" aria-hidden="true"></span>${['overview', 'modules', 'activity'].map(name => `<a data-route href="${routes[name]}" data-nav="${name}">${icon(name)}<span>${name.charAt(0).toUpperCase() + name.slice(1)}</span></a>`).join('')}</nav></div><div class="mast-right"><div id="update-slot"></div><button type="button" id="bell" data-popover-trigger class="icon-button notification-trigger" aria-expanded="false" aria-controls="notification-panel" aria-label="Notifications">${icon('bell')}<span id="unread-indicator" hidden></span></button><div id="notification-panel" class="popover notification-panel" role="dialog" aria-label="Notifications" hidden></div><a data-route data-nav="settings" href="${routes.settings}" class="icon-button settings-link" aria-label="Settings" title="Settings">${icon('settings')}</a><button type="button" id="account" class="account" data-popover-trigger aria-expanded="false" aria-controls="account-menu" aria-label="Account"><span class="avatar" aria-hidden="true">${esc(username.charAt(0).toUpperCase())}</span></button><div id="account-menu" class="popover account-menu" role="dialog" aria-label="Account" hidden><div class="account-who">${icon('user')}<div><span class="quiet-text">Signed in as</span><strong>${esc(username)}</strong></div></div><button type="button" id="logout" class="menu-item">${icon('signout')}<span>Sign out</span></button></div></div></header><main class="content" id="content" tabindex="-1"></main><aside id="drawer" class="drawer" aria-hidden="true" hidden></aside></div>`;
  document.querySelector('#product-switch').onclick = event => { renderSwitcher(); togglePopover(document.querySelector('#product-menu'), event.currentTarget); };
  document.querySelector('#bell').onclick = async event => {
    renderNotificationPanel();
    togglePopover(document.querySelector('#notification-panel'), event.currentTarget);
    if (openPopover?.panel.id === 'notification-panel') {
      try { notices = await api('/notifications'); if (username && document.querySelector('.shell')) updateChrome(); }
      catch (error) { toast(error.message, 'error'); }
    }
  };
  document.querySelector('#account').onclick = event => togglePopover(document.querySelector('#account-menu'), event.currentTarget);
  document.querySelector('#version-button').onclick = () => { closePopovers(); releaseDialog(); };
  document.querySelector('#logout').onclick = async () => {
    try { await api('/auth/logout', { method: 'POST' }); username = ''; csrf = ''; system = null; refreshEpoch++; closePopovers(); auth(false); }
    catch (error) { toast(error.message, 'error'); }
  };
}
function updateChrome() {
  const unread = notices.filter(n => !n.read).length;
  const indicator = document.querySelector('#unread-indicator');
  const was = indicator.hidden;
  indicator.hidden = !unread; indicator.textContent = unread > 99 ? '99+' : unread;
  if (was && unread) animate(indicator, [{ transform: 'scale(.4)', opacity: 0 }, { transform: 'scale(1)', opacity: 1 }], { duration: 220, easing: 'cubic-bezier(.34,1.4,.64,1)' });
  document.querySelector('#bell').setAttribute('aria-label', `Notifications${unread ? `, ${unread} unread` : ''}`);
  document.querySelector('#version-button').innerHTML = `<span>Nexus v${esc(system.version)}</span><span class="quiet-text">${esc(hasUpdate() ? 'Update available' : 'Release information')}</span>`;
  const slot = document.querySelector('#update-slot');
  slot.innerHTML = hasUpdate() ? `<button type="button" class="update-pill" id="update-card">${icon('upgrade')}<span>Nexus ${esc(system.update.version)} available</span></button>` : '';
  document.querySelector('#update-card')?.addEventListener('click', releaseDialog);
  if (openPopover?.panel.id === 'notification-panel') renderNotificationPanel();
}
function placeInk() {
  const nav = document.querySelector('.nav'), ink = document.querySelector('.nav-ink');
  const active = nav?.querySelector('a.active');
  if (!ink) return;
  if (!active) { ink.style.opacity = '0'; return; }
  ink.style.opacity = '1';
  ink.style.width = `${active.offsetWidth}px`;
  ink.style.transform = `translateX(${active.offsetLeft}px)`;
}
function renderSwitcher() {
  const items = document.querySelector('#launcher-items');
  const current = view.name === 'module' ? view.id : 'nexus';
  const apps = modules.filter(m => m.state === 'enabled');
  items.innerHTML = `<a data-route href="${routes.overview}" class="launcher-item${current === 'nexus' ? ' current' : ''}"><span class="launcher-glyph nexus">${MARK}</span><span class="launcher-text"><strong>Nexus</strong><small>Control center</small></span>${current === 'nexus' ? icon('check', 'tick') : ''}</a>${apps.map(m => `<a data-route class="launcher-item${current === m.id ? ' current' : ''}" href="/app/modules/${m.id}">${monogram(m)}<span class="launcher-text"><strong>${esc(m.manifest.name)}</strong><small>${esc(status(m).label)} · v${esc(m.manifest.version)}</small></span>${current === m.id ? icon('check', 'tick') : ''}</a>`).join('')}<a data-route class="launcher-manage" href="${routes.modules}">${icon('modules')}<span>Manage modules</span>${icon('chevronRight', 'end')}</a>`;
}
function notificationItems(items) {
  return items.length ? items.map(n => `<article class="notification ${n.read ? '' : 'unread'}">${icon(n.source === 'nexus' ? 'spark' : 'message', 'notice-glyph')}<div><p>${esc(n.message)}</p><div class="notification-meta"><span>${esc(n.source === 'nexus' ? 'Nexus' : moduleName(n.source))}</span><span aria-hidden="true">·</span><time datetime="${esc(n.created_at)}" title="${esc(date(n.created_at))}">${esc(relative(n.created_at))}</time>${!n.read ? '<span class="unread-label">Unread</span>' : ''}</div></div></article>`).join('')
    : `<div class="empty-compact">${icon('bell')}<p>Nothing needs your attention.</p></div>`;
}
function renderNotificationPanel() {
  const panel = document.querySelector('#notification-panel');
  panel.innerHTML = `<div class="popover-heading"><h2>Notifications</h2><div id="panel-read-action"></div></div><div class="notification-scroll">${notificationItems(notices.slice(0, 6))}</div><a data-route class="popover-footer" href="${routes.notifications}">All notifications${icon('chevronRight', 'end')}</a>`;
  if (notices.some(n => !n.read)) panel.querySelector('#panel-read-action').append(action('Mark all read', markNotificationsRead, 'quiet small', 'Saving…'));
}
async function markNotificationsRead() {
  await api('/notifications/read', { method: 'POST' });
  notices = await api('/notifications'); updateChrome();
  if (view.name === 'notifications' || view.name === 'overview') renderView();
}
function heading(label, extra = '', sub = '') {
  return `<div class="page-heading"><div><h1 tabindex="-1">${esc(label)}</h1>${sub ? `<p class="page-sub">${sub}</p>` : ''}</div><div class="heading-actions" id="heading-action">${extra}</div></div>`;
}

/* ─────────────── Views ─────────────── */

const ORDER = ['overview', 'modules', 'activity', 'settings'];
async function renderView({ transition = false, focus = false, changed = null, added = [], from = null } = {}) {
  const epoch = ++renderEpoch;
  const content = document.querySelector('#content');
  if (!content) return;
  const module = view.name === 'module' ? modules.find(m => m.id === view.id) : null;
  const appMode = !!(module?.state === 'enabled' && isApplication(module));
  document.body.classList.toggle('application-mode', appMode);
  const navName = view.name === 'notifications' ? '' : view.name === 'module' ? '' : view.name;
  document.querySelectorAll('[data-nav]').forEach(link => {
    const active = link.dataset.nav === navName;
    link.classList.toggle('active', active);
    if (active) link.setAttribute('aria-current', 'page'); else link.removeAttribute('aria-current');
  });
  placeInk();
  document.querySelector('#product-name').textContent = module?.manifest.name || system.name;
  const pageTitle = view.name === 'module' ? (module?.manifest.name || 'Module') : view.name === 'not-found' ? 'Not found' : view.name.charAt(0).toUpperCase() + view.name.slice(1);
  document.title = `${pageTitle} · Empyrean Nexus`;
  if (view.name === 'overview') await renderOverview(content, epoch);
  else if (view.name === 'modules') renderModules(content);
  else if (view.name === 'settings') renderSettings(content);
  else if (view.name === 'activity') {
    content.innerHTML = heading('Activity') + skeleton();
    try {
      const data = await api('/activity/entries');
      if (epoch !== renderEpoch) return;
      renderActivity(content, data);
    } catch (error) { if (epoch === renderEpoch) content.innerHTML = heading('Activity') + `<p role="alert" class="error-text">${esc(error.message)}</p>`; }
  } else if (view.name === 'notifications') {
    content.innerHTML = heading('Notifications', '', 'Messages from Nexus and your modules, newest first.') + `<section class="notification-history">${notificationItems(notices)}</section>`;
    if (notices.some(n => !n.read)) document.querySelector('#heading-action').append(action('Mark all read', markNotificationsRead, '', 'Saving…'));
  } else if (view.name === 'module') renderModuleView(content, module);
  else content.innerHTML = `<div class="empty-state">${icon('info', 'empty-glyph')}<h1 tabindex="-1">Page not found</h1><p>This address isn't part of Nexus.</p><a data-route class="button-link" href="${routes.overview}">Go to Overview</a></div>`;
  if (epoch !== renderEpoch) return;
  if (transition && !appMode) {
    const a = ORDER.indexOf(from?.name), b = ORDER.indexOf(view.name);
    if (a >= 0 && b >= 0 && a !== b) slideIn(content, b > a ? 1 : -1); else enter(content);
    stagger(content.querySelectorAll('.module-row, .overview-app'));
  }
  if (!transition && added.length) stagger(added.map(id => document.querySelector(`[data-module-id="${CSS.escape(id)}"]`)).filter(Boolean));
  if (changed && !added.includes(changed)) feedback(document.querySelector(`[data-module-id="${CSS.escape(changed)}"]`));
  if (focus && !appMode) content.querySelector('h1')?.focus({ preventScroll: true });
}

async function renderOverview(content, epoch) {
  const attention = modules.filter(m => status(m).attention);
  const pending = modules.filter(m => status(m).tone === 'pending');
  const running = modules.filter(m => m.state === 'enabled');
  const unread = notices.filter(n => !n.read);
  const tone = attention.length ? 'bad' : pending.length ? 'pending' : 'good';
  const headline = !modules.length ? 'Your platform is ready'
    : attention.length ? `${plural(attention.length, 'module needs', 'modules need')} attention`
      : pending.length ? `${esc(pending[0].manifest.name)} is ${status(pending[0]).label.replace('…', '').toLowerCase()}`
        : 'Everything is running normally';
  const sub = [`Nexus ${esc(system.version)}`, modules.length ? `${running.length} of ${plural(modules.length, 'module', 'modules')} running` : 'No modules installed', `${bytes(system.data_free_bytes)} free for data`].join(' · ');
  const apps = modules.filter(m => m.state !== 'removing');
  content.innerHTML = `<section class="hero tone-${tone}"><div class="hero-orb" aria-hidden="true">${icon(tone === 'bad' ? 'alert' : tone === 'pending' ? 'refresh' : 'check')}</div><div class="hero-text"><p class="eyebrow">${esc(system.name)}</p><h1 tabindex="-1">${headline}</h1><p class="hero-sub">${sub}</p></div><div class="heading-actions" id="heading-action"></div></section>
    ${attention.length ? `<section class="attention" aria-label="Needs attention">${attention.map(m => `<div class="attention-row" data-module-id="${esc(m.id)}">${monogram(m)}<div class="attention-text"><strong>${esc(m.manifest.name)} · ${esc(status(m).label)}</strong><span>${esc(status(m).hint || '')}</span></div><div class="attention-actions" data-attention="${esc(m.id)}"></div></div>`).join('')}</section>` : ''}
    ${unread.length ? `<button type="button" class="notice-line" id="unread-line">${icon('bell')}<span>${plural(unread.length, 'unread notification', 'unread notifications')}</span>${icon('chevronRight', 'end')}</button>` : ''}
    <div class="overview-grid">
      <section class="overview-section" aria-labelledby="apps-heading"><header class="section-head"><h2 id="apps-heading">Modules</h2><a data-route href="${routes.modules}" class="section-link">Manage${icon('chevronRight')}</a></header>
        ${apps.length ? `<div class="overview-apps">${apps.map(m => `<div class="overview-app" data-module-id="${esc(m.id)}">${monogram(m)}<div class="overview-app-text"><strong>${esc(m.manifest.name)}</strong><span>${statusPill(m)}<span class="quiet-text">v${esc(m.manifest.version)}</span></span></div>${canOpen(m) ? `<a data-route class="button-link small" href="/app/modules/${esc(m.id)}">Open</a>` : ''}</div>`).join('')}</div>`
          : `<div class="empty-inline"><p>Modules are the applications this platform runs — notes, places, people. Install one from its reviewed manifest.</p><button type="button" class="primary" id="overview-install">${icon('plus')}Install a module</button></div>`}
      </section>
      <section class="overview-section" aria-labelledby="recent-heading"><header class="section-head"><h2 id="recent-heading">Recent activity</h2><a data-route href="${routes.activity}" class="section-link">All activity${icon('chevronRight')}</a></header><div id="overview-activity">${skeleton()}</div></section>
    </div>
    <section class="platform" aria-labelledby="platform-heading"><h2 id="platform-heading">Platform</h2><dl class="facts"><div><dt>Version</dt><dd>Nexus ${esc(system.version)} <button type="button" class="link-button" id="overview-release">${esc(hasUpdate() ? 'Update available' : 'Release information')}</button></dd></div><div><dt>Updates</dt><dd>${esc(updateLabel())}</dd></div><div><dt>Data volume</dt><dd>${bytes(system.data_free_bytes)} free</dd></div><div><dt>Database</dt><dd>${esc(system.database || 'SQLite')}</dd></div><div><dt>Module protocol</dt><dd>v${esc(system.protocol)}</dd></div></dl></section>`;
  document.querySelector('#heading-action').append(action('Refresh', () => refresh(), 'quiet small', 'Refreshing…'));
  document.querySelector('#overview-release').onclick = releaseDialog;
  document.querySelector('#overview-install')?.addEventListener('click', installDialog);
  document.querySelector('#unread-line')?.addEventListener('click', event => { event.stopPropagation(); document.querySelector('#bell').click(); });
  for (const holder of content.querySelectorAll('[data-attention]')) {
    const m = modules.find(x => x.id === holder.dataset.attention);
    holder.append(action('Details', () => openDrawer(m.id, { navigate: true }), 'quiet small'));
    if (m.state === 'error') holder.append(action('Stop and clean up', () => lifecycle(m, 'disable'), 'small', 'Stopping…'));
    else holder.append(action('Check again', () => health(m), 'small', 'Checking…'));
  }
  try {
    const data = await api('/activity/entries?limit=12');
    if (epoch !== renderEpoch) return;
    const holder = document.querySelector('#overview-activity');
    const items = settleRequests(data.items).slice(0, 6);
    holder.innerHTML = items.length ? `<ol class="timeline compact">${items.map(activityRow).join('')}</ol>` : '<p class="quiet-text">Nothing has happened yet.</p>';
  } catch {
    const holder = document.querySelector('#overview-activity');
    if (holder && epoch === renderEpoch) holder.innerHTML = '<p class="quiet-text">Recent activity is unavailable right now.</p>';
  }
}

function moduleRow(m) {
  const s = status(m);
  return `<article class="module-row" data-module-id="${esc(m.id)}" tabindex="0" role="listitem" aria-label="${esc(m.manifest.name)}, ${esc(s.label)}">${monogram(m)}<div class="module-main"><div class="module-title"><h3>${esc(m.manifest.name)}</h3><span class="version">v${esc(m.manifest.version)}</span>${isApplication(m) ? '' : '<span class="tag">Service</span>'}</div><p class="module-desc">${esc(m.manifest.description || '')}</p></div><div class="module-state">${statusPill(m)}${s.hint ? `<small>${esc(s.hint)}</small>` : ''}</div><div class="actions" data-actions="${esc(m.id)}"></div></article>`;
}
function renderModules(content) {
  const running = modules.filter(m => m.state === 'enabled').length;
  content.innerHTML = heading('Modules', '', modules.length ? `${plural(modules.length, 'module', 'modules')} installed · ${running} running` : 'Nothing installed yet') + (modules.length ? `<div class="module-list" role="list" id="module-list">${modules.map(moduleRow).join('')}</div>` : `<div class="empty-state">${MARK}<h2>No modules yet</h2><p>A module is an application or service that runs on this platform. You review exactly what it may do before it is installed, and it stays stopped until you start it.</p><button type="button" class="primary" id="empty-install">${icon('plus')}Install a module</button></div>`);
  const actions = document.querySelector('#heading-action');
  actions.append(action('Refresh', () => refresh(), 'quiet', 'Refreshing…'), action('Install module', installDialog, 'primary'));
  document.querySelector('#empty-install')?.addEventListener('click', installDialog);
  for (const holder of content.querySelectorAll('[data-actions]')) fillRowActions(holder, modules.find(m => m.id === holder.dataset.actions));
}
function fillRowActions(holder, m) {
  const pending = status(m).tone === 'pending';
  if (canOpen(m)) {
    const link = document.createElement('a'); link.className = 'button-link'; link.href = `/app/modules/${m.id}`; link.dataset.route = ''; link.textContent = 'Open';
    holder.append(link);
  } else if (m.state === 'disabled' || m.state === 'error') {
    const start = action(m.state === 'error' ? 'Retry start' : 'Start', () => lifecycle(m, 'enable'), 'primary', 'Starting…');
    start.disabled = pending;
    holder.append(start);
  }
  const more = document.createElement('button');
  more.type = 'button'; more.className = 'icon-button row-more'; more.dataset.popoverTrigger = ''; more.setAttribute('aria-haspopup', 'menu'); more.setAttribute('aria-expanded', 'false');
  more.setAttribute('aria-label', `More actions for ${m.manifest.name}`);
  more.innerHTML = icon('more');
  more.disabled = pending;
  more.onclick = () => menu(more, moduleMenu(m));
  holder.append(more);
}
function moduleMenu(m) {
  const items = [{ label: 'Details', icon: 'info', run: () => openDrawer(m.id) }];
  if (m.state === 'enabled') items.push({ label: 'Check health', icon: 'pulse', run: () => health(m) }, { label: 'Stop', icon: 'stop', run: () => lifecycle(m, 'disable') });
  if (m.state === 'error') items.push({ label: 'Stop and clean up', icon: 'stop', run: () => lifecycle(m, 'disable') });
  if (supports().recovery) {
    items.push({ label: 'Review an update…', icon: 'upgrade', run: () => updateDialog(m), disabled: !['enabled', 'disabled', 'error'].includes(m.state) });
    if (m.manifest.backup) items.push({ label: 'Back up now', icon: 'history', run: () => createBackup(m), disabled: m.state !== 'enabled' });
  }
  items.push({ separator: true }, { label: 'Uninstall…', icon: 'trash', danger: true, run: () => uninstallDialog(m) });
  return items;
}
async function health(module) {
  pendingOps.set(module.id, 'Checking…');
  patchModule(module.id);
  try {
    const result = await api(`/modules/${module.id}/health`, { method: 'POST' });
    pendingOps.delete(module.id);
    await refresh({ changed: module.id });
    const words = { healthy: 'is healthy', unhealthy: 'reported a problem', unreachable: 'is not responding', disabled: 'is stopped' };
    toast(`${module.manifest.name} ${words[result.status] || result.status}.`, ['unreachable', 'unhealthy'].includes(result.status) ? 'error' : 'success');
  } finally { pendingOps.delete(module.id); patchModule(module.id); }
}
async function lifecycle(module, operation) {
  pendingOps.set(module.id, operation === 'enable' ? 'Starting…' : 'Stopping…');
  patchModule(module.id);
  try {
    await api(`/modules/${module.id}/${operation}`, { method: 'POST' });
    pendingOps.delete(module.id);
    await refresh({ changed: module.id });
    toast(`${module.manifest.name} ${operation === 'enable' ? 'is running' : 'stopped'}.`);
  } catch (error) { pendingOps.delete(module.id); await refresh({ changed: module.id }); throw error; }
  finally { pendingOps.delete(module.id); patchModule(module.id); }
}
/** Re-renders the visible representations of one module in place. */
function patchModule(id) {
  const m = modules.find(x => x.id === id);
  if (!m) return;
  const row = document.querySelector(`.module-row[data-module-id="${CSS.escape(id)}"]`);
  if (row) {
    const template = document.createElement('template');
    template.innerHTML = moduleRow(m).trim();
    const next = template.content.firstElementChild;
    const hadFocus = row === document.activeElement;
    row.replaceWith(next);
    fillRowActions(next.querySelector('[data-actions]'), m);
    if (hadFocus) next.focus();
  }
  if (drawerId === id) renderDrawer();
}

/* ─────────────── Module details drawer ─────────────── */

function openDrawer(id, { navigate = false } = {}) {
  if (navigate && view.name !== 'modules') {
    router.navigate(routes.modules);
  }
  const drawer = document.querySelector('#drawer');
  if (!drawer || !modules.some(m => m.id === id)) return;
  const wasOpen = !drawer.hidden;
  drawerId = id;
  renderDrawer();
  drawer.hidden = false;
  drawer.setAttribute('aria-hidden', 'false');
  document.querySelector('.shell').classList.add('drawer-open');
  document.querySelectorAll('.module-row.is-selected').forEach(r => r.classList.remove('is-selected'));
  document.querySelector(`.module-row[data-module-id="${CSS.escape(id)}"]`)?.classList.add('is-selected');
  if (!wasOpen) animate(drawer, [{ opacity: 0, transform: 'translateX(24px)' }, { opacity: 1, transform: 'none' }], { duration: 230 });
  drawer.querySelector('h2')?.focus({ preventScroll: true });
}
async function closeDrawer(restoreFocus = true) {
  const drawer = document.querySelector('#drawer');
  const id = drawerId;
  drawerId = null;
  if (!drawer || drawer.hidden) return;
  document.querySelector('.shell')?.classList.remove('drawer-open');
  document.querySelectorAll('.module-row.is-selected').forEach(r => r.classList.remove('is-selected'));
  await animate(drawer, [{ opacity: 1, transform: 'none' }, { opacity: 0, transform: 'translateX(24px)' }], { duration: 160, easing: 'cubic-bezier(.4,0,1,1)', fill: 'forwards' });
  if (drawerId) return;
  drawer.hidden = true;
  drawer.setAttribute('aria-hidden', 'true');
  drawer.innerHTML = '';
  if (restoreFocus && id) document.querySelector(`.module-row[data-module-id="${CSS.escape(id)}"]`)?.focus();
}
function renderDrawer() {
  const drawer = document.querySelector('#drawer');
  const m = modules.find(x => x.id === drawerId);
  if (!drawer || !m) return;
  const manifest = m.manifest, s = status(m), refs = manifest.references;
  const events = manifest.events || { produces: [], consumes: [] };
  const persistent = manifest.capabilities.includes('storage.data');
  const features = supports();
  drawer.innerHTML = `<div class="drawer-inner" data-drawer-module="${esc(m.id)}">
    <header class="drawer-head">${monogram(m, 'large')}<div class="drawer-title"><h2 tabindex="-1">${esc(manifest.name)}</h2><div class="drawer-sub">${statusPill(m)}<span class="quiet-text">v${esc(manifest.version)}</span></div></div><button type="button" class="icon-button" id="drawer-close" aria-label="Close details">${icon('close')}</button></header>
    ${manifest.description ? `<p class="drawer-desc">${esc(manifest.description)}</p>` : ''}
    ${s.hint ? `<p class="drawer-note tone-${s.tone}">${esc(s.hint)}</p>` : ''}
    <div class="drawer-actions" id="drawer-actions"></div>
    <section class="d-section"><h3>What it may do</h3>${capabilityRows(manifest.capabilities)}</section>
    ${(events.produces.length || events.consumes.length) ? `<section class="d-section"><h3>Events</h3><dl class="facts tight">${events.produces.length ? `<div><dt>Announces</dt><dd>${events.produces.map(e => `<code>${esc(e)}</code>`).join(' ')}</dd></div>` : ''}${events.consumes.length ? `<div><dt>Listens for</dt><dd>${events.consumes.map(e => `<code>${esc(e)}</code>`).join(' ')}</dd></div>` : ''}</dl></section>` : ''}
    ${refs && (refs.read?.length || refs.resolve?.length || (manifest.resources || []).length) ? `<section class="d-section"><h3>Links with other modules</h3><dl class="facts tight">${(manifest.resources || []).length ? `<div><dt>Items others can link to</dt><dd>${manifest.resources.map(r => `${esc(r.type)}${r.resolvable ? '' : ' <span class="quiet-text">(not resolvable)</span>'}`).join(', ')}</dd></div>` : ''}${refs.read?.length ? `<div><dt>Can see shared links about</dt><dd>${refs.read.map(scopeText).join(', ')}</dd></div>` : ''}${refs.resolve?.length ? `<div><dt>Can look up titles of</dt><dd>${refs.resolve.map(scopeText).join(', ')}</dd></div>` : ''}</dl><p class="quiet-text">Seeing a link never reveals the linked item's contents.</p></section>` : ''}
    <section class="d-section"><h3>Data</h3><p class="d-text">${persistent ? 'Keeps its data in a private volume on this server. Stopping, updating or uninstalling the module keeps that data.' : 'Declares no persistent storage. Anything it holds is gone when it stops.'}</p></section>
    ${features.trust ? `<section class="d-section"><h3>Trusted sites</h3>${(m.external_origins || []).length ? `<ul class="trusted-origins" id="trusted-origins"></ul>` : '<p class="quiet-text">None. When this module wants to open an external site, Nexus asks you first.</p>'}</section>` : ''}
    ${features.recovery ? `<section class="d-section" id="update-section"><h3>Updates</h3><p class="d-text">Nexus doesn't discover module releases. To update, review the new version's manifest; nothing changes until you approve it.</p><div class="d-actions" id="update-actions"></div><div id="update-history"></div></section>` : ''}
    ${features.recovery ? `<section class="d-section" id="backup-section"><h3>Backups</h3>${manifest.backup ? `<div class="d-actions" id="backup-actions"></div><div id="backup-list">${skeleton()}</div>` : `<p class="d-text">This module doesn't support Nexus backups${persistent ? '. Its data volume must be backed up with the rest of the server' : ''}.</p>`}</section>` : ''}
    <details class="d-section technical"><summary>${icon('chevronRight', 'disclosure')}Technical details</summary><div class="details-body"><dl class="facts tight"><div><dt>Identifier</dt><dd><code>${esc(m.id)}</code></dd></div><div><dt>Image</dt><dd><code class="wrap">${esc(manifest.container?.image || "—")}</code></dd></div><div><dt>Internal port</dt><dd>${esc(m.port ?? manifest.container?.port ?? "—")}</dd></div><div><dt>Installed</dt><dd>${esc(date(m.installed_at))}</dd></div><div><dt>Source</dt><dd>${esc(m.source)}</dd></div><div><dt>Publisher</dt><dd>${esc(manifest.publisher?.name || '—')} <span class="quiet-text">(self-declared)</span></dd></div><div><dt>Provenance</dt><dd>${esc(m.provenance?.review || 'Unverified')}</dd></div><div><dt>Requires Nexus</dt><dd><code>${esc(manifest.nexus || "—")}</code></dd></div><div><dt>Last health</dt><dd>${esc(m.health)}</dd></div></dl><pre>${esc(JSON.stringify(manifest, null, 2))}</pre></div></details>
  </div>`;
  drawer.querySelector('#drawer-close').onclick = () => closeDrawer(true);
  const actions = drawer.querySelector('#drawer-actions');
  const pending = s.tone === 'pending';
  if (canOpen(m)) { const link = document.createElement('a'); link.className = 'button-link primary'; link.href = `/app/modules/${m.id}`; link.dataset.route = ''; link.innerHTML = `${icon('open')}Open`; actions.append(link); }
  if (m.state === 'enabled') actions.append(action('Check health', () => health(m), '', 'Checking…'), action('Stop', () => lifecycle(m, 'disable'), '', 'Stopping…'));
  if (m.state === 'disabled' || m.state === 'error') actions.append(action(m.state === 'error' ? 'Retry start' : 'Start', () => lifecycle(m, 'enable'), 'primary', 'Starting…'));
  if (m.state === 'error') actions.append(action('Stop and clean up', () => lifecycle(m, 'disable'), '', 'Stopping…'));
  const more = document.createElement('button');
  more.type = 'button'; more.className = 'icon-button'; more.dataset.popoverTrigger = ''; more.setAttribute('aria-haspopup', 'menu'); more.setAttribute('aria-label', 'More actions'); more.innerHTML = icon('more');
  more.onclick = () => menu(more, moduleMenu(m).filter(item => item.label !== 'Details' && item.label !== 'Check health' && item.label !== 'Stop' && item.label !== 'Stop and clean up'));
  actions.append(more);
  if (pending) actions.querySelectorAll('button').forEach(b => { b.disabled = true; });
  const list = drawer.querySelector('#trusted-origins');
  (m.external_origins || []).forEach(origin => {
    const item = document.createElement('li');
    const name = document.createElement('code'); name.textContent = origin;
    item.append(name, action('Remove', async () => {
      const result = await api(`/modules/${m.id}/external-origins?origin=${encodeURIComponent(origin)}`, { method: 'DELETE' });
      m.external_origins = result.external_origins;
      await collapse(item);
      toast(`${m.manifest.name} can no longer open ${origin} without asking.`);
    }, 'quiet small', 'Removing…'));
    list?.append(item);
  });
  if (features.recovery) {
    drawer.querySelector('#update-actions').append(action('Review an update…', () => updateDialog(m), '', 'Opening…'));
    loadUpdateHistory(m);
    if (manifest.backup) {
      const create = action('Back up now', () => createBackup(m), '', 'Backing up…');
      create.disabled = m.state !== 'enabled';
      drawer.querySelector('#backup-actions').append(create);
      if (m.state !== 'enabled') drawer.querySelector('#backup-actions').insertAdjacentHTML('beforeend', '<span class="quiet-text">Start the module to back it up.</span>');
      loadBackups(m);
    }
  }
}
async function loadUpdateHistory(m) {
  try {
    const rows = await api(`/modules/${m.id}/updates`);
    const holder = document.querySelector('#update-history');
    if (!holder || drawerId !== m.id) return;
    holder.innerHTML = rows.length ? `<ol class="mini-list">${rows.slice(0, 5).map(r => `<li><span>${esc(r.from_version)} → ${esc(r.to_version)}</span><span class="state-word state-${esc(r.state)}">${esc(r.state === 'completed' ? 'Completed' : r.state === 'failed' ? `Failed at ${r.stage}` : r.state)}</span><time class="quiet-text" title="${esc(date(r.updated_at || r.started_at))}">${esc(relative(r.updated_at || r.started_at))}</time></li>`).join('')}</ol>` : '';
  } catch { /* Update history is supplementary. */ }
}
async function loadBackups(m) {
  const holder = document.querySelector('#backup-list');
  try {
    const [backups, restores] = await Promise.all([api(`/modules/${m.id}/backups`), api(`/modules/${m.id}/restores`)]);
    if (!holder || drawerId !== m.id || !holder.isConnected) return;
    const attention = restores.filter(r => r.state === 'needs_attention');
    holder.innerHTML = `${attention.map(r => `<div class="drawer-note tone-bad" data-restore="${esc(r.id)}"><strong>A restore needs attention</strong> at the ${esc(r.stage)} step: ${esc(r.detail)}. Automatic cleanups stay paused until it is finalized.<div class="d-actions" data-finalize="${esc(r.id)}"></div></div>`).join('')}${backups.length ? `<ol class="mini-list backups">${backups.map(b => `<li data-backup="${esc(b.id)}"><div><strong title="${esc(date(b.exported_at || b.created_at))}">${esc(relative(b.exported_at || b.created_at))}</strong><span class="quiet-text">v${esc(b.module_version)} · ${bytes(b.artifact?.size)}${b.blobs?.length ? ` · ${plural(b.blobs.length, 'file', 'files')}` : ''}</span></div><div class="d-actions" data-backup-actions="${esc(b.id)}"></div></li>`).join('')}</ol>` : '<p class="quiet-text">No backups yet.</p>'}${restores.length ? `<p class="quiet-text">Last restore: ${esc(restores[0].state.replace('_', ' '))} · ${esc(relative(restores[0].updated_at))}</p>` : ''}`;
    for (const el of holder.querySelectorAll('[data-finalize]')) el.append(action('Finish restore', async () => {
      await api(`/modules/${m.id}/restores/${el.dataset.finalize}/finalize`, { method: 'POST' });
      toast('Restore finished. Automatic cleanups resumed.');
      await refresh({ changed: m.id });
    }, 'primary small', 'Finishing…'));
    for (const el of holder.querySelectorAll('[data-backup-actions]')) {
      const id = el.dataset.backupActions, backup = backups.find(b => b.id === id);
      const link = document.createElement('a'); link.className = 'button-link small quiet'; link.href = `/api/v1/modules/${encodeURIComponent(m.id)}/backups/${encodeURIComponent(id)}/download`; link.setAttribute('download', ''); link.innerHTML = `${icon('download')}Download`;
      const restore = action('Restore…', () => restoreDialog(m, backup), 'quiet small');
      // Nexus refuses a restore the backup's version range excludes; say so before anyone tries.
      const exact = /^==\s*([0-9A-Za-z.+-]+)$/.exec(backup.restorable_by || '');
      if (exact && exact[1] !== m.manifest.version) {
        restore.disabled = true;
        restore.title = `Only version ${exact[1]} can restore this backup`;
        el.closest('li').querySelector('.quiet-text').insertAdjacentText('beforeend', ` · restorable by v${exact[1]} only`);
      }
      el.append(link, restore);
    }
  } catch (error) { if (holder?.isConnected) holder.innerHTML = `<p class="error-text">${esc(error.message)}</p>`; }
}
async function createBackup(m) {
  const result = await api(`/modules/${m.id}/backups`, { method: 'POST' });
  toast(`Backed up ${m.manifest.name} (${bytes(result.artifact?.size)}).`);
  if (drawerId === m.id) loadBackups(m);
}
function restoreDialog(m, backup) {
  modal(`Restore ${m.manifest.name}?`, `<p>This replaces ${esc(m.manifest.name)}'s current data with the backup from <strong>${esc(date(backup.exported_at || backup.created_at))}</strong> (version ${esc(backup.module_version)}). Changes made since then are lost unless you back up first.</p><ul class="plain-list"><li>The module is paused while its data is replaced.</li><li>Automatic cleanups stay paused until the restore is finalized.</li><li>Its links in the reference index are rebuilt from the restored data where the module supports it.</li></ul><label class="check-line"><input type="checkbox" id="confirm-replace"> Replace the current data</label><div class="dialog-actions" id="restore-actions"></div>`);
  const context = dialogEpoch;
  dialog.querySelector('#restore-actions').append(action('Cancel', closeDialog, 'quiet'), action('Restore backup', async () => {
    if (!dialog.querySelector('#confirm-replace').checked) throw new Error('Confirm that the current data will be replaced.');
    try {
      const result = await api(`/modules/${m.id}/backups/${backup.id}/restore`, { method: 'POST', body: JSON.stringify({ confirm_replace: true }) });
      if (context === dialogEpoch) await closeDialog();
      toast(result.warnings?.length ? `Restored with a warning: ${result.warnings.join(' ')}` : `${m.manifest.name} was restored.`, result.warnings?.length ? 'error' : 'success');
    } finally { await refresh({ changed: m.id }); }
  }, 'danger', 'Restoring…'));
}

/* ─────────────── Install, update and uninstall reviews ─────────────── */

function manifestInput(prefix) {
  return `<div class="manifest-input"><label for="${prefix}-manifest">Manifest</label><textarea id="${prefix === 'install' ? 'manifest' : prefix + '-manifest'}" spellcheck="false" placeholder="Paste the module's JSON manifest"></textarea><div class="file-line"><label class="button-link small quiet" for="${prefix}-file">${icon('file')}Choose a file…</label><input id="${prefix}-file" class="visually-hidden" type="file" accept=".json,application/json"><span class="quiet-text">Up to 64 KiB</span></div></div>`;
}
function reviewIdentity(manifest, badge) {
  return `<div class="review-identity">${monogram({ manifest, id: manifest.id }, 'large')}<div><h3>${esc(manifest.name)} <span class="quiet-text">v${esc(manifest.version)}</span></h3><p>${esc(manifest.description || '')}</p><div class="review-badges">${badge}<span class="tag">Publisher: ${esc(manifest.publisher?.name || 'unknown')} (self-declared)</span></div></div></div>`;
}
function installDialog() {
  modal('Install a module', `<p class="lede">Nexus shows you exactly what a module may do before anything runs. Installing only registers it; it stays stopped until you start it.</p><div id="sample-action"></div>${manifestInput('install')}<p class="error-text" id="review-error" role="alert"></p><div id="review-result"></div><div class="dialog-actions" id="install-actions"></div>`, { wide: true });
  const context = dialogEpoch;
  const text = dialog.querySelector('#manifest'), result = dialog.querySelector('#review-result');
  if (system?.development?.reference_module) dialog.querySelector('#sample-action').append(action('Load reference manifest', async () => { text.value = JSON.stringify(await api('/example-manifest'), null, 2); result.innerHTML = ''; }, 'quiet', 'Loading…'));
  dialog.querySelector('#install-file').onchange = async event => {
    const file = event.target.files[0];
    if (file && file.size <= 65536) { text.value = await file.text(); result.innerHTML = ''; }
    else toast('Choose a manifest smaller than 64 KiB.', 'error');
  };
  text.oninput = () => { result.innerHTML = ''; };
  const reviewButton = action('Review permissions', async () => {
    try {
      const reviewedText = text.value;
      const manifest = JSON.parse(reviewedText);
      const review = await api('/modules/validate', { method: 'POST', body: JSON.stringify(manifest) });
      if (context !== dialogEpoch || text.value !== reviewedText) return;
      const retained = review.retained_references || review.retained_data;
      result.innerHTML = `<div class="review">${reviewIdentity(manifest, '<span class="tag warn">Community · unreviewed</span>')}<p class="warning-text">${icon('shield')}${esc(review.warning)}</p><h4>It asks permission to</h4>${capabilityRows(review.capabilities)}${manifest.references ? `<h4>Links with other modules</h4><dl class="facts tight">${manifest.references.read?.length ? `<div><dt>Can see shared links about</dt><dd>${manifest.references.read.map(scopeText).join(', ')}</dd></div>` : ''}${manifest.references.resolve?.length ? `<div><dt>Can look up titles of</dt><dd>${manifest.references.resolve.map(scopeText).join(', ')}</dd></div>` : ''}${(manifest.resources || []).length ? `<div><dt>Items others can link to</dt><dd>${manifest.resources.map(r => esc(r.type)).join(', ')}</dd></div>` : ''}</dl><p class="quiet-text">Read scopes never reveal private relationships. Looking up a title shows only what the owning module agrees to share.</p>` : ''}<details class="technical"><summary>${icon('chevronRight', 'disclosure')}Technical details</summary><div class="details-body"><dl class="facts tight"><div><dt>Identifier</dt><dd><code>${esc(manifest.id)}</code></dd></div><div><dt>Image</dt><dd><code class="wrap">${esc(manifest.container.image)}</code></dd></div><div><dt>Internal port</dt><dd>${esc(manifest.container.port)}</dd></div><div><dt>Requires Nexus</dt><dd><code>${esc(manifest.nexus)}</code></dd></div></dl>${manifest.references ? `<pre>${esc(JSON.stringify(manifest.references, null, 2))}</pre>` : ''}</div></details>${retained ? `<div class="drawer-note tone-pending"><strong>This identity was used before.</strong> ${plural(review.retained_references || 0, 'retained reference', 'retained references')}${review.retained_data ? ' and persistent data' : ''} belong to <code>${esc(manifest.id)}</code>.<label class="check-line"><input type="checkbox" id="reuse-identity"> Restore this identity with the same resource IDs. A different dataset could misdirect existing references.</label></div>` : ''}<label class="check-line consent"><input type="checkbox" id="consent"> Grant the permissions and scopes shown above.</label><div id="confirm-install" class="dialog-actions"></div></div>`;
      result.querySelector('#confirm-install').append(action('Install (stays stopped)', async () => {
        if (!dialog.querySelector('#consent').checked) throw new Error('Review and grant the requested capabilities first.');
        if ((review.retained_references || review.retained_data) && !dialog.querySelector('#reuse-identity').checked) throw new Error('Confirm that you are restoring the same resource identity.');
        await api('/modules', { method: 'POST', body: JSON.stringify({ manifest, grants: review.capabilities, reuse_reference_identity: !!(review.retained_references || review.retained_data) }) });
        if (context === dialogEpoch) closeDialog(); await refresh({ changed: manifest.id }); toast(`${manifest.name} is installed. Start it when you're ready.`);
      }, 'primary', 'Installing…'));
      dialog.querySelector('#review-error').textContent = ''; enter(result);
      reviewButton.hidden = true;
    } catch (error) { result.innerHTML = ''; dialog.querySelector('#review-error').textContent = error.message; }
  }, 'primary', 'Validating…');
  text.addEventListener('input', () => { reviewButton.hidden = false; });
  dialog.querySelector('#install-actions').append(reviewButton);
}
function diffList(label, diff, tone) {
  if (!diff || (!diff.added?.length && !diff.removed?.length)) return '';
  return `<div class="diff-row"><dt>${esc(label)}</dt><dd>${diff.added.map(x => `<span class="chip add">+ ${esc(x)}</span>`).join('')}${diff.removed.map(x => `<span class="chip remove">− ${esc(x)}</span>`).join('')}</dd></div>`;
}
function updateDialog(m) {
  modal(`Update ${m.manifest.name}`, `<p class="lede">Paste the new version's manifest. Nexus compares it with what is installed; nothing changes until you approve.</p>${manifestInput('update')}<p class="error-text" id="update-error" role="alert"></p><div id="update-review"></div><div class="dialog-actions" id="update-actions-row"></div>`, { wide: true });
  const context = dialogEpoch;
  const text = dialog.querySelector('#update-manifest'), result = dialog.querySelector('#update-review');
  dialog.querySelector('#update-file').onchange = async event => {
    const file = event.target.files[0];
    if (file && file.size <= 65536) { text.value = await file.text(); result.innerHTML = ''; }
    else toast('Choose a manifest smaller than 64 KiB.', 'error');
  };
  const reviewButton = action('Review changes', async () => {
    try {
      const reviewedText = text.value;
      const manifest = JSON.parse(reviewedText);
      const diff = await api(`/modules/${m.id}/update/review`, { method: 'POST', body: JSON.stringify(manifest) });
      if (context !== dialogEpoch || text.value !== reviewedText) return;
      const added = diff.capabilities.added, removed = diff.capabilities.removed;
      const direction = diff.downgrade === true ? '<span class="tag bad">Downgrade</span>' : diff.downgrade === null ? '<span class="tag warn">Direction unknown</span>' : '<span class="tag good">Upgrade</span>';
      const backupText = { recommended: 'A backup before updating is recommended.', unavailable: 'This module can\'t be backed up by Nexus. Back up its data volume another way first if it matters.', not_applicable: 'This module keeps no persistent data.' }[diff.backup];
      result.innerHTML = `<div class="review"><div class="version-change"><span>v${esc(diff.from_version)}</span>${icon('arrow')}<strong>v${esc(diff.to_version)}</strong>${direction}</div>
        ${added.length ? `<h4 class="attention-heading">${icon('shield')}New permissions it asks for</h4>${capabilityRows(added, { tone: 'added' })}` : '<p class="good-text">No new permissions.</p>'}
        ${removed.length ? `<h4>Permissions it gives up</h4>${capabilityRows(removed, { tone: 'removed' })}` : ''}
        <dl class="facts diff">${diffList('Links it can see', diff.reference_scopes.read)}${diffList('Titles it can look up', diff.reference_scopes.resolve)}${diffList('Item types', diff.resources)}${diffList('Events announced', diff.events.produces)}${diffList('Events listened for', diff.events.consumes)}<div class="diff-row"><dt>Container image</dt><dd>${diff.image_changed ? 'Changes' : 'Unchanged'}</dd></div>${diff.port.from !== diff.port.to ? `<div class="diff-row"><dt>Internal port</dt><dd>${esc(diff.port.from)} → ${esc(diff.port.to)}</dd></div>` : ''}${diff.nexus_range.from !== diff.nexus_range.to ? `<div class="diff-row"><dt>Requires Nexus</dt><dd><code>${esc(diff.nexus_range.from)}</code> → <code>${esc(diff.nexus_range.to)}</code></dd></div>` : ''}<div class="diff-row"><dt>Data</dt><dd>${esc(diff.persistent_data === 'none' ? 'No persistent data' : 'Existing data is kept' + (diff.persistent_data.includes('no longer') ? ', but the new version no longer mounts it' : ''))}</dd></div><div class="diff-row"><dt>Migrations</dt><dd>${esc(diff.migrations)}</dd></div><div class="diff-row"><dt>Restart</dt><dd>${m.state === 'disabled' ? 'Stays stopped; health is checked when you start it.' : 'The module restarts and must pass a health check. No automatic rollback.'}</dd></div></dl>
        <p class="quiet-text">${esc(backupText || '')}</p>
        ${diff.backup === 'recommended' ? '<label class="check-line"><input type="checkbox" id="backup-before" checked> Back up before updating (the update stops if the backup fails)</label>' : ''}
        ${added.length ? '<label class="check-line consent"><input type="checkbox" id="grant-new"> Grant the new permissions listed above</label>' : ''}
        ${diff.downgrade !== false ? `<label class="check-line"><input type="checkbox" id="allow-downgrade"> ${diff.downgrade ? 'I understand data written by the newer version may not be readable' : 'Apply even though the version direction can\'t be determined'}</label>` : ''}
        <div class="dialog-actions" id="apply-update"></div></div>`;
      result.querySelector('#apply-update').append(action(`Update to v${diff.to_version}`, async () => {
        if (added.length && !dialog.querySelector('#grant-new').checked) throw new Error('Grant the new permissions first, or cancel.');
        if (diff.downgrade !== false && !dialog.querySelector('#allow-downgrade').checked) throw new Error('Confirm the version change first.');
        pendingOps.set(m.id, 'Updating…'); patchModule(m.id);
        try {
          const outcome = await api(`/modules/${m.id}/update`, { method: 'POST', body: JSON.stringify({ manifest, grants: manifest.capabilities, backup_before: !!dialog.querySelector('#backup-before')?.checked, allow_downgrade: diff.downgrade !== false }) });
          if (context === dialogEpoch) await closeDialog();
          toast(outcome.state === 'enabled' ? `${m.manifest.name} is now v${diff.to_version} and healthy.` : `${m.manifest.name} is now v${diff.to_version}. Start it to verify its health.`);
        } finally { pendingOps.delete(m.id); await refresh({ changed: m.id }); }
      }, 'primary', 'Updating — waiting for the health check…'));
      reviewButton.hidden = true;
      dialog.querySelector('#update-error').textContent = ''; enter(result);
    } catch (error) { result.innerHTML = ''; dialog.querySelector('#update-error').textContent = error.message; }
  }, 'primary', 'Comparing…');
  text.addEventListener('input', () => { result.innerHTML = ''; reviewButton.hidden = false; });
  dialog.querySelector('#update-actions-row').append(reviewButton);
}
function uninstallDialog(module) {
  const persistent = module.manifest.capabilities.includes('storage.data');
  const data = persistent
    ? 'Its persistent data volume is retained, not deleted; reinstalling the same module can reuse it after explicit confirmation.'
    : 'This module declares no persistent storage; data inside its container is not kept.';
  modal(`Uninstall ${module.manifest.name}?`, `<p>This stops and removes the module's container and network, revokes its credentials and releases port ${esc(module.port)}.</p><p class="d-text">${data}</p><p class="quiet-text">Nexus activity history, shared files and resource references are retained; references may become unresolved.</p><div class="dialog-actions" id="remove-actions"></div>`);
  const context = dialogEpoch;
  dialog.querySelector('#remove-actions').append(action('Cancel', closeDialog, 'quiet'), action('Uninstall', async () => {
    await api('/modules/' + module.id, { method: 'DELETE' }); if (context === dialogEpoch) closeDialog();
    if (drawerId === module.id) closeDrawer(false);
    const row = document.querySelector(`.module-row[data-module-id="${CSS.escape(module.id)}"]`);
    if (row) await collapse(row);
    await refresh(); toast(`${module.manifest.name} was uninstalled.`);
  }, 'danger', 'Removing…'));
}

/* ─────────────── Module view ─────────────── */

function renderModuleView(content, module) {
  if (!module) { content.innerHTML = `<div class="empty-state">${icon('modules', 'empty-glyph')}<h1 tabindex="-1">Module not installed</h1><p>Nothing called “${esc(view.id)}” is installed on this platform.</p><a data-route class="button-link" href="${routes.modules}">Manage modules</a></div>`; return; }
  if (module.state !== 'enabled') {
    const s = status(module);
    content.innerHTML = `<div class="empty-state">${monogram(module, 'large')}<h1 tabindex="-1">${esc(module.manifest.name)} isn't running</h1><p>${statusPill(module)} ${esc(s.hint || '')}</p><div class="heading-actions" id="heading-action"></div></div>`;
    if (module.state === 'disabled' || module.state === 'error') document.querySelector('#heading-action').append(action('Start', () => lifecycle(module, 'enable'), 'primary', 'Starting…'));
    const manage = document.createElement('a'); manage.className = 'button-link'; manage.href = routes.modules; manage.dataset.route = ''; manage.textContent = 'Manage modules';
    document.querySelector('#heading-action').append(manage);
    return;
  }
  const path = view.modulePath || '/';
  if (isApplication(module)) {
    content.innerHTML = `<iframe id="module-application" title="${esc(module.manifest.name)}" sandbox="allow-scripts allow-downloads" src="/modules/${module.id}${esc(path)}"></iframe>`;
    return;
  }
  content.innerHTML = heading(module.manifest.name, `<a data-route class="button-link" href="${routes.modules}">Manage modules</a>`, `${statusPill(module)} <span class="quiet-text">v${esc(module.manifest.version)} · sandboxed module view</span>`) + `<section class="module-frame"><iframe title="${esc(module.manifest.name)}" sandbox="allow-scripts" src="/modules/${module.id}${esc(path)}"></iframe></section><details class="api-explorer"><summary>${icon('chevronRight', 'disclosure')}Module API explorer</summary><div class="details-body"><label for="module-api-path">Path relative to <code>${esc(module.manifest.routes.api)}</code></label><div class="explorer-line"><input id="module-api-path" value="/info" maxlength="100"><div class="dialog-actions inline" id="module-api-actions"></div></div><pre id="module-api-result" aria-live="polite"></pre></div></details>`;
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

/* ─────────────── Settings ─────────────── */

function renderSettings(content) {
  content.innerHTML = heading('Settings') + `<div class="settings">
    <section class="setting-group"><div class="setting-intro"><h2>Installation</h2><p>How this Nexus names itself, and the language modules use for dates and text.</p></div><form id="settings-form" class="setting-form"><label for="name">Installation name</label><input id="name" value="${esc(system.name)}" maxlength="80" required><label for="locale">Language tag</label><input id="locale" value="${esc(system.locale || 'en')}" maxlength="35" aria-describedby="locale-help"><p class="help" id="locale-help">For example <code>en</code>, <code>en-GB</code> or <code>sk</code>.</p><div><button class="primary" type="submit">Save changes</button></div></form></section>
    <section class="setting-group"><div class="setting-intro"><h2>This Nexus</h2><p>The control plane's version and release information.</p></div><div><dl class="facts"><div><dt>Version</dt><dd>Nexus ${esc(system.version)}</dd></div><div><dt>Updates</dt><dd>${esc(updateLabel())}</dd></div><div><dt>Data volume</dt><dd>${bytes(system.data_free_bytes)} free</dd></div><div><dt>Database</dt><dd>${esc(system.database || 'SQLite')}</dd></div><div><dt>Module protocol</dt><dd>v${esc(system.protocol)}</dd></div></dl><button type="button" class="quiet" id="settings-release">${icon('info')}Release information</button></div></section>
    <section class="setting-group"><div class="setting-intro"><h2>Your data</h2><p>Nexus metadata: settings, module manifests, references, retained events, notifications and activity. Credentials are never included.</p></div><div><a class="button-link" href="/api/v1/export" download="nexus-export.json">${icon('download')}Download metadata export</a><p class="help">An export is not a restorable backup, and it can contain private information. Keep it safe.</p></div></section>
    <section class="setting-group"><div class="setting-intro"><h2>Developers</h2><p>Machine-readable contracts for building modules.</p></div><div class="link-stack"><a href="/api/v1/openapi.json" target="_blank" rel="noopener">OpenAPI description ↗</a><a href="/api/v1/protocol" target="_blank" rel="noopener">Module manifest schema ↗</a></div></section>
    <section class="setting-group"><div class="setting-intro"><h2>Account</h2><p>You are signed in as <strong>${esc(username)}</strong>, the administrator of this installation.</p></div><div><button type="button" class="quiet" id="settings-logout">${icon('signout')}Sign out</button></div></section>
  </div>`;
  document.querySelector('#settings-release').onclick = releaseDialog;
  document.querySelector('#settings-logout').onclick = () => document.querySelector('#logout').click();
  document.querySelector('#settings-form').onsubmit = async event => {
    event.preventDefault(); const button = event.target.querySelector('button');
    button.disabled = true; button.classList.add('is-busy'); button.textContent = 'Saving…';
    try { await api('/settings', { method: 'PATCH', body: JSON.stringify({ installation_name: document.querySelector('#name').value, locale: document.querySelector('#locale').value }) }); await refresh(); toast('Settings saved.'); }
    catch (error) { toast(error.message, 'error'); }
    finally { button.disabled = false; button.classList.remove('is-busy'); button.textContent = 'Save changes'; }
  };
}

/* ─────────────── Activity ─────────────── */

const ACTIVITY_GLYPH = { enable: 'play', disable: 'stop', uninstall: 'trash', installed: 'plus', health: 'pulse', update: 'upgrade', backup: 'history', restore: 'history', references: 'link', external: 'globe', compatibility: 'alert' };
function activityText(item) {
  const kind = item.kind;
  const fixed = { 'setup.completed': ['Nexus was set up', 'spark'], 'auth.login': ['Signed in', 'user'], 'settings.changed': ['Settings changed', 'settings'], 'metadata.exported': ['Metadata exported', 'download'] };
  if (fixed[kind]) return { text: fixed[kind][0], glyph: fixed[kind][1], tone: '' };
  if (kind.startsWith('module.')) {
    const [, verb, outcome] = kind.split('.');
    const name = moduleName(item.subject);
    const failed = outcome === 'failed';
    const requested = outcome === 'requested';
    const phrases = {
      enable: [`Starting ${name}`, `${name} started`, `${name} failed to start`],
      disable: [`Stopping ${name}`, `${name} stopped`, `${name} failed to stop`],
      uninstall: [`Removing ${name}`, `${name} uninstalled`, `Removing ${name} failed`],
      update: [`Updating ${name}`, `${name} updated`, `Updating ${name} failed`],
      restore: [`Restoring ${name}`, `${name} restored`, `Restoring ${name} failed`],
      backup: [`Backing up ${name}`, outcome === 'exported' ? `A backup of ${name} was downloaded` : `${name} backed up`, `Backing up ${name} failed`],
      references: [`Rebuilding ${name}'s links`, `${name}'s links were rebuilt`, `Rebuilding ${name}'s links failed`],
    };
    let text;
    if (verb === 'installed') text = `${name} installed`;
    else if (verb === 'health') text = { healthy: `${name} is healthy`, unhealthy: `${name} reported a problem`, unreachable: `${name} stopped responding`, disabled: `${name} is stopped` }[outcome] || `${name} health: ${outcome}`;
    else if (verb === 'external') text = outcome === 'trusted' ? `A site was trusted for ${name}` : `A trusted site was removed from ${name}`;
    else if (verb === 'compatibility') text = `${name} is not compatible with this Nexus`;
    else if (phrases[verb]) text = phrases[verb][failed ? 2 : requested ? 0 : 1];
    else text = `${name}: ${[verb, outcome].filter(Boolean).join(' ')}`;
    return { text, glyph: ACTIVITY_GLYPH[verb] || 'modules', tone: failed || verb === 'compatibility' || (verb === 'health' && outcome !== 'healthy') ? 'bad' : requested ? 'quiet' : '' };
  }
  return { text: kind.replace(/[._]/g, ' '), glyph: 'info', tone: '' };
}
// A request whose outcome is already recorded adds nothing but noise; the technical view keeps it.
function settleRequests(items) {
  if (showCodes) return items;
  const outcomes = new Set();
  return items.filter(item => {
    const [scope, verb, outcome] = item.kind.split('.');
    if (scope !== 'module' || !outcome) return true;
    const key = `${verb}:${item.subject}`;
    if (outcome === 'requested') return !outcomes.has(key);
    outcomes.add(key);
    return true;
  });
}
function activityRow(item) {
  const a = activityText(item);
  return `<li class="activity-row tone-${a.tone || 'normal'}">${icon(a.glyph, 'activity-glyph')}<div class="activity-text"><span>${esc(a.text)}</span>${showCodes ? `<code>${esc(item.kind)} · ${esc(item.subject)}</code>` : ''}</div><span class="activity-actor">${esc(item.actor)}</span><time datetime="${esc(item.occurred_at)}" title="${esc(date(item.occurred_at))}">${esc(clock(item.occurred_at))}</time></li>`;
}
function renderActivity(content, data) {
  content.innerHTML = heading('Activity', '', 'What happened on this platform, newest first.') + '<div class="activity" id="activity-list"></div><div id="activity-more"></div>';
  const heads = document.querySelector('#heading-action');
  heads.append(action('Refresh', () => renderView(), 'quiet', 'Refreshing…'));
  const codes = document.createElement('button');
  codes.type = 'button'; codes.className = 'quiet'; codes.setAttribute('aria-pressed', String(showCodes)); codes.textContent = showCodes ? 'Hide event codes' : 'Show event codes';
  codes.onclick = () => { showCodes = !showCodes; renderView(); };
  heads.append(codes);
  let lastDay = null;
  const append = raw => {
    const items = settleRequests(raw);
    const list = document.querySelector('#activity-list');
    if (!items.length && !list.children.length) list.innerHTML = `<div class="empty-state small">${icon('activity', 'empty-glyph')}<p>No activity recorded yet.</p></div>`;
    items.forEach(item => {
      const label = dayLabel(item.occurred_at);
      if (label !== lastDay) {
        lastDay = label;
        list.insertAdjacentHTML('beforeend', `<h2 class="day-heading">${esc(label)}</h2><ol class="timeline"></ol>`);
      }
      list.lastElementChild.insertAdjacentHTML('beforeend', activityRow(item));
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
    }, 'quiet', 'Loading…');
    document.querySelector('#activity-more').append(button);
  }
}
function safeReleaseURL(value) { try { const url = new URL(value); return url.protocol === 'https:' && !url.username && !url.password ? url.href : null; } catch { return null; } }
function releaseDialog() {
  const update = system.update, release = hasUpdate() ? update : (system.release || {});
  const source = safeReleaseURL(release.url);
  modal('Nexus release', `<dl class="facts"><div><dt>Installed version</dt><dd>v${esc(system.version)}</dd></div><div><dt>Update status</dt><dd>${esc(updateLabel())}</dd></div>${hasUpdate() ? `<div><dt>Available version</dt><dd>v${esc(update.version)}</dd></div>` : ''}${release.published_at ? `<div><dt>Release date</dt><dd>${esc(date(release.published_at))}</dd></div>` : ''}${source ? `<div><dt>Release source</dt><dd><a href="${esc(source)}" target="_blank" rel="noopener noreferrer">${esc(new URL(source).hostname)} ↗</a></dd></div>` : ''}</dl>${release.notes ? `<h3>Release notes</h3><pre>${esc(release.notes)}</pre>` : ''}<p class="help">${system.update.discovery_supported ? 'Opening release information does not install an update.' : 'Update discovery is not configured. Nexus has not checked for a newer release.'}</p>${hasUpdate() ? '<p class="help">Automatic installation is not implemented. Review the deployment instructions before updating.</p>' : ''}`);
}

/* ─────────────── Display typeface ─────────────── */

function detectDisplayFont() {
  if (!document.fonts?.load) return;
  document.fonts.load('32px "Nexus Display"', 'EMPYREAN NEXUS').then(faces => {
    if (faces.length) document.documentElement.classList.add('has-display-font');
  }).catch(() => {});
}
window.addEventListener('resize', () => { placeInk(); if (openPopover?.transient) closePopovers(); });

detectDisplayFont();
router.start();
(async () => {
  try {
    const setup = await api('/setup');
    if (setup.required) { auth(true); return; }
    try { const session = await api('/auth/session'); csrf = session.csrf; username = session.username; }
    catch { auth(false); return; }
    await refresh({ initial: true });
  } catch (error) {
    app.innerHTML = `<main class="loading unavailable">${MARK}<h1>Nexus is unavailable</h1><p>${esc(error.message)}</p><button type="button" class="primary" id="retry">Try again</button></main>`;
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
