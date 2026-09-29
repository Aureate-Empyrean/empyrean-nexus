// Shared motion primitives. Motion never gates a network action or changes its outcome.
export const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const active = new WeakMap();
function token(name, fallback) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}
export async function animate(element, frames, options = {}) {
  if (!element || reducedMotion() || !element.animate) return;
  active.get(element)?.cancel();
  const animation = element.animate(frames, {
    duration: parseInt(token('--motion-normal', '200'), 10),
    fill: 'backwards',
    easing: token('--motion-ease', 'cubic-bezier(.2,.7,.2,1)'),
    ...options,
  });
  active.set(element, animation);
  try { await animation.finished; } catch { /* A newer UI state superseded this transition. */ }
  if (active.get(element) === animation) active.delete(element);
}
export const enter = (element, options = {}) => animate(element, [
  { opacity: 0, transform: 'translateY(6px)' }, { opacity: 1, transform: 'translateY(0)' },
], options);
export const leave = element => animate(element, [
  { opacity: 1, transform: 'translateY(0)' }, { opacity: 0, transform: 'translateY(3px)' },
], { duration: 140 });
export function stagger(elements) {
  [...elements].forEach((element, index) => enter(element, { delay: Math.min(index * 25, 100) }));
}
export function feedback(element) {
  return animate(element, [{ backgroundColor: 'rgba(214,173,96,.12)' }, { backgroundColor: 'transparent' }], { duration: 300 });
}
export async function toggleDetails(details) {
  if (details.dataset.animating) return;
  const body = details.querySelector('.details-body');
  if (!body || reducedMotion()) { details.open = !details.open; return; }
  details.dataset.animating = 'true';
  if (details.open) {
    await animate(body, [{ height: `${body.offsetHeight}px`, opacity: 1 }, { height: '0px', opacity: 0 }], { duration: 160 });
    details.open = false;
  } else {
    details.open = true;
    await animate(body, [{ height: '0px', opacity: 0 }, { height: `${body.offsetHeight}px`, opacity: 1 }]);
  }
  delete details.dataset.animating;
}
