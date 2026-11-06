// This event is an invalidation signal, never evidence that the tutor is available.
export async function assessmentChanged(request) {
  const response = await request;
  window.dispatchEvent(new Event('trace:assessment-changed'));
  try {
    localStorage.setItem('trace:assessment-changed', String(Date.now()) + ':' + Math.random());
  } catch (_) { /* Same-tab events still work when storage is unavailable. */ }
  return response;
}
