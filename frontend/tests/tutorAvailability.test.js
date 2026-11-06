import { it, expect, vi } from 'vitest';
import { createTutorAvailability } from '../src/services/tutorAvailability';
const result = (available) => ({ tutor_availability: { available, exam_type: available ? null : 'pre' } });
it('coalesces concurrent checks and fails closed when status is missing', async () => {
  const fetch = vi.fn().mockResolvedValue({}); const store = createTutorAvailability(fetch);
  const first = store.refresh(); expect(store.refresh()).toBe(first); await first;
  expect(fetch).toHaveBeenCalledTimes(1); expect(store.getSnapshot().status).toBe('error');
});
it('a policy rejection wins over an older successful status response', async () => {
  let resolve; const store = createTutorAvailability(() => new Promise((done) => { resolve = done; }));
  const request = store.refresh(); await Promise.resolve();
  store.reportLocked({ exam_type: 'pre' }); resolve(result(true)); await request;
  expect(store.getSnapshot().status).toBe('locked');
});
it('assessment invalidation queues a fresh check instead of trusting an old response', async () => {
  let resolve; const fetch = vi.fn().mockImplementationOnce(() => new Promise((done) => { resolve = done; })).mockResolvedValue(result(false));
  const store = createTutorAvailability(fetch); const request = store.refresh(); await Promise.resolve();
  store.invalidate(); resolve(result(true)); await request;
  expect(fetch).toHaveBeenCalledTimes(2); expect(store.getSnapshot().status).toBe('locked');
});

it('refreshes quietly without republishing a confirmed available state', async () => {
  let resolve;
  const fetch = vi.fn().mockResolvedValueOnce(result(true)).mockImplementationOnce(() => new Promise((done) => { resolve = done; }));
  const store = createTutorAvailability(fetch);
  await store.refresh();
  const listener = vi.fn(); store.subscribe(listener);
  const request = store.refresh({ background: true }); await Promise.resolve();
  expect(store.getSnapshot().status).toBe('available'); expect(listener).not.toHaveBeenCalled();
  resolve(result(true)); await request;
  expect(listener).not.toHaveBeenCalled();
});
it('quiet refresh still applies genuine locks and fails closed on errors', async () => {
  const fetch = vi.fn().mockResolvedValueOnce(result(true)).mockResolvedValueOnce(result(false)).mockRejectedValueOnce(new Error('offline'));
  const store = createTutorAvailability(fetch); await store.refresh();
  await store.refresh({ background: true }); expect(store.getSnapshot().status).toBe('locked');
  await store.refresh({ background: true }); expect(store.getSnapshot().status).toBe('error');
});
it('waits for queued checks before a submission can use refreshed eligibility', async () => {
  let resolve;
  const fetch = vi.fn().mockResolvedValueOnce(result(true)).mockImplementationOnce(() => new Promise((done) => { resolve = done; })).mockResolvedValueOnce(result(false));
  const store = createTutorAvailability(fetch); await store.refresh();
  const background = store.refresh({ background: true }); await Promise.resolve();
  const submissionCheck = store.refresh();
  store.invalidate({ background: true }); resolve(result(true));
  await submissionCheck; await background;
  expect(store.getSnapshot().status).toBe('locked'); expect(fetch).toHaveBeenCalledTimes(3);
});
