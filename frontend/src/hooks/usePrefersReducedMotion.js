/**
 * Does this viewer ask for reduced motion?
 *
 * Read during render rather than written into state from an effect: the answer decides
 * what to show, so deriving it keeps the reduced-motion path from rendering one frame
 * of animation before an effect can switch it off.
 */
export function prefersReducedMotion() {
  try {
    return Boolean(window.matchMedia?.('(prefers-reduced-motion: reduce)').matches);
  } catch (_) {
    return false;
  }
}
