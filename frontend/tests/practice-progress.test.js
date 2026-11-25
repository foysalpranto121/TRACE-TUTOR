import { afterEach, expect, it, vi } from 'vitest';
import { apiService } from '../src/services/api';
import { computeXp, evaluateBadges } from '../src/data/gamification';

vi.mock('../src/services/session', () => ({ getToken: () => 'test-token', clearSession: vi.fn() }));
afterEach(() => vi.unstubAllGlobals());

it('identifies practice runs so the server can choose the checks', async () => {
  const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ status: 'SUCCESS' }) });
  vi.stubGlobal('fetch', fetch);
  await apiService.runCode('c', 'source', [], 'run', 'prob_c_loop_101');
  expect(JSON.parse(fetch.mock.calls[0][1].body)).toMatchObject({ problem_id: 'prob_c_loop_101', mode: 'run' });
});

it('keeps generic assessment runs outside the practice counter', async () => {
  const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ status: 'OK' }) });
  vi.stubGlobal('fetch', fetch);
  await apiService.runCode('c', 'source', [], 'check');
  expect(JSON.parse(fetch.mock.calls[0][1].body)).not.toHaveProperty('problem_id');
});

it('legacy success logs do not earn current completion XP or completion badges', () => {
  const snapshot = { stats: { problems_solved: 8 }, problems: [{ problem_id: 'prob_c_loop_101', solved: true }] };
  expect(computeXp(snapshot.stats)).toBe(0);
  expect(evaluateBadges(snapshot).some((badge) => badge.earned)).toBe(false);
});

it('awards practice credit for checked tasks without claiming independent authorship', () => {
  expect(computeXp({ practice_tasks_passed: 3 })).toBe(300);
  const badges = evaluateBadges({ stats: { practice_tasks_passed: 3 } });
  expect(badges.find((badge) => badge.id === 'practice_three').earned).toBe(true);
  expect(badges.some((badge) => badge.title === 'Independent')).toBe(false);
});
