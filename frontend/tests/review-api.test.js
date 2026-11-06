import { afterEach, expect, it, vi } from 'vitest';
import { apiService, ApiError } from '../src/services/api';
vi.mock('../src/services/session', () => ({ getToken: () => 'disposable-token', clearSession: vi.fn() }));
afterEach(() => vi.unstubAllGlobals());
it('sends complete ratings and an explicit null revision for the first submission', async () => {
  const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ rated: true }) }); vi.stubGlobal('fetch', fetch);
  const ratings = { alignment: 4, accuracy: 3, clarity: 2, difficulty: 1, answerability: 4 };
  await apiService.submitExpertRating('qa-item', ratings, 'Disposable feedback', null);
  expect(fetch.mock.calls[0][0]).toBe('/api/expert/rating/');
  expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ item_id: 'qa-item', ratings, feedback: 'Disposable feedback', expected_revision: null });
});
it('keeps genuine zero marks and carries the grade revision to the server', async () => {
  const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ assigned_marks: 0 }) }); vi.stubGlobal('fetch', fetch);
  await apiService.gradeSubmission(1, 0, 'Disposable grade', 'original-version');
  expect(fetch.mock.calls[0][0]).toBe('/api/expert/grade/');
  expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ submission_id: 1, assigned_marks: 0, feedback: 'Disposable grade', expected_revision: 'original-version' });
});
it('returns structured conflict failures so the form can preserve drafts and offer recovery', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 409, statusText: 'Conflict', json: async () => ({ error: 'Review changed', reason: 'review_conflict' }) }));
  await expect(apiService.gradeSubmission(1, 70, 'Draft', 'stale')).rejects.toMatchObject({ name: 'Error', status: 409, body: { reason: 'review_conflict' } });
  expect(ApiError.prototype instanceof Error).toBe(true);
});
