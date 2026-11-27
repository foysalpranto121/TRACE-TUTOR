import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { apiService } from '../src/services/api';
import { getToken, loadSession, saveSession } from '../src/services/session';

const token = 'a'.repeat(40);
const expiredResponse = () => ({ ok: false, status: 401, statusText: 'Unauthorized',
  json: async () => ({ detail: 'Invalid token.' }) });

beforeEach(() => {
  localStorage.clear(); sessionStorage.clear();
  saveSession({ id: 1, username: 'first' }, token);
});
afterEach(() => { vi.unstubAllGlobals(); localStorage.clear(); sessionStorage.clear(); });

it('does not let an old profile request expire a newly logged-in account', async () => {
  let respond;
  vi.stubGlobal('fetch', vi.fn(() => new Promise((resolve) => { respond = resolve; })));
  const expired = vi.fn();
  window.addEventListener('trace:session-expired', expired);
  try {
    const request = apiService.me();
    saveSession({ id: 2, username: 'second' }, 'b'.repeat(40));
    respond(expiredResponse());
    await expect(request).rejects.toMatchObject({ status: 401 });
    expect(loadSession().user.id).toBe(2);
    expect(getToken()).toBe('b'.repeat(40));
    expect(expired).not.toHaveBeenCalled();
  } finally { window.removeEventListener('trace:session-expired', expired); }
});

it('still expires the currently authenticated session when its token is rejected', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => expiredResponse()));
  const expired = vi.fn();
  window.addEventListener('trace:session-expired', expired);
  try {
    await expect(apiService.me()).rejects.toMatchObject({ status: 401 });
    expect(loadSession().user).toBeNull();
    expect(getToken()).toBeNull();
    expect(expired).toHaveBeenCalledOnce();
  } finally { window.removeEventListener('trace:session-expired', expired); }
});

it('does not expire a newer login when a delayed logout explicitly sends the old token', async () => {
  saveSession({ id: 2, username: 'second' }, 'b'.repeat(40));
  const fetch = vi.fn(async () => expiredResponse());
  vi.stubGlobal('fetch', fetch);
  const expired = vi.fn();
  window.addEventListener('trace:session-expired', expired);
  try {
    await expect(apiService.logout(token)).rejects.toMatchObject({ status: 401 });
    expect(fetch.mock.calls[0][1].headers.Authorization).toBe(`Token ${token}`);
    expect(loadSession().user.id).toBe(2);
    expect(getToken()).toBe('b'.repeat(40));
    expect(expired).not.toHaveBeenCalled();
  } finally { window.removeEventListener('trace:session-expired', expired); }
});
