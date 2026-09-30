// Shared motion primitives. Motion follows state; it never gates a network action,
// never changes an outcome and never implies that an operation finished early.
export const reducedMotion = () => !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
const active = new WeakMap();
function token(name, fallback) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}
export async function animate(element, frames, options = {}) {
  if (!element || reducedMotion() || !element.animate) return;
  active.get(element)?.cancel();
  const animation = element.animate(frames, {
    duration: parseInt(token('--motion-normal', '180'), 10),
    fill: 'backwards',
    easing: token('--motion-ease', 'cubic-bezier(.2,.8,.2,1)'),
    ...options,
  });
  active.set(element, animation);
  try { await animation.finished; } catch { /* A newer UI state superseded this transition. */ }
  // A forwards-filled exit keeps its end state until the next transition on the element
  // cancels it; forgetting it here would leave the element invisible when it is shown again.
  if (active.get(element) === animation && !String(options.fill || '').includes('forwards')) active.delete(element);
}
export const enter = (element, options = {}) => animate(element, [
  { opacity: 0, transform: 'translateY(6px)' }, { opacity: 1, transform: 'translateY(0)' },
], options);
export const slideIn = (element, direction = 1) => animate(element, [
  { opacity: 0, transform: `translateX(${direction * 14}px)` }, { opacity: 1, transform: 'translateX(0)' },
], { duration: 220 });
export const leave = element => animate(element, [
  { opacity: 1, transform: 'translateY(0)' }, { opacity: 0, transform: 'translateY(3px)' },
], { duration: 120, easing: 'cubic-bezier(.4,0,1,1)', fill: 'forwards' });
export function stagger(elements) {
  [...elements].forEach((element, index) => enter(element, { delay: Math.min(index * 24, 96) }));
}
export function feedback(element) {
  return animate(element, [{ backgroundColor: 'rgba(214,173,96,.14)' }, { backgroundColor: 'rgba(214,173,96,0)' }], { duration: 700 });
}
/** Removes an element by collapsing its height; immediate under reduced motion. */
export async function collapse(element) {
  if (!element) return;
  if (!reducedMotion() && element.animate) {
    element.style.overflow = 'hidden';
    await animate(element, [
      { height: `${element.offsetHeight}px`, opacity: 1 },
      { height: '0px', opacity: 0, paddingTop: '0px', paddingBottom: '0px', marginTop: '0px', marginBottom: '0px' },
    ], { duration: 200, easing: 'cubic-bezier(.4,0,1,1)', fill: 'forwards' });
  }
  element.remove();
}
/** Grows a newly inserted element from zero height. */
export function expand(element) {
  if (!element || reducedMotion() || !element.animate) return;
  element.style.overflow = 'hidden';
  animate(element, [{ height: '0px', opacity: 0 }, { height: `${element.offsetHeight}px`, opacity: 1 }], { duration: 200 })
    .then(() => { element.style.overflow = ''; });
}
/** Measures keyed children, applies a DOM change, then glides moved children into place. */
export function flip(container, selector, change) {
  const before = new Map([...container.querySelectorAll(selector)].map(el => [el.dataset.key, el.getBoundingClientRect()]));
  change();
  if (reducedMotion()) return;
  for (const el of container.querySelectorAll(selector)) {
    const old = before.get(el.dataset.key);
    if (!old) { expand(el); continue; }
    const now = el.getBoundingClientRect();
    const dy = old.top - now.top;
    if (dy) animate(el, [{ transform: `translateY(${dy}px)` }, { transform: 'translateY(0)' }], { duration: 220 });
  }
}
export async function toggleDetails(details) {
  if (details.dataset.animating) return;
  const body = details.querySelector('.details-body');
  if (!body || reducedMotion()) { details.open = !details.open; return; }
  details.dataset.animating = 'true';
  if (details.open) {
    await animate(body, [{ height: `${body.offsetHeight}px`, opacity: 1 }, { height: '0px', opacity: 0 }], { duration: 150, easing: 'cubic-bezier(.4,0,1,1)', fill: 'forwards' });
    details.open = false;
  } else {
    details.open = true;
    await animate(body, [{ height: '0px', opacity: 0 }, { height: `${body.offsetHeight}px`, opacity: 1 }]);
  }
  delete details.dataset.animating;
}
