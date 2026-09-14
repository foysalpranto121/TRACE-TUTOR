// Session persistence: "remember me" keeps the session in localStorage, otherwise it lives in sessionStorage.
const USER_KEY = 'trace_user';
const TOKEN_KEY = 'trace_auth_token';
const TOKEN_RE = /^[a-f0-9]{40}$/;

function stores() {
  const out = [];
  try { out.push(window.sessionStorage); } catch (_) { /* unavailable */ }
  try { out.push(window.localStorage); } catch (_) { /* unavailable */ }
  return out;
}

export function loadSession() {
  for (const store of stores()) {
    try {
      const raw = store.getItem(USER_KEY);
      if (raw && raw !== 'undefined') {
        return { user: JSON.parse(raw), token: store.getItem(TOKEN_KEY), store };
      }
    } catch (_) { /* corrupt entry */ }
  }
  return { user: null, token: null, store: null };
}

export function saveSession(user, token, remember = true) {
  clearSession();
  const store = remember ? window.localStorage : window.sessionStorage;
  try {
    store.setItem(USER_KEY, JSON.stringify(user));
    if (token) store.setItem(TOKEN_KEY, token);
  } catch (_) { /* storage blocked */ }
}

export function updateSessionUser(user) {
  const { store } = loadSession();
  try { (store || window.localStorage).setItem(USER_KEY, JSON.stringify(user)); } catch (_) { /* storage blocked */ }
}

export function updateSessionToken(token) {
  const { store } = loadSession();
  try { (store || window.localStorage).setItem(TOKEN_KEY, token); } catch (_) { /* storage blocked */ }
}

export function clearSession() {
  for (const store of stores()) {
    try { store.removeItem(USER_KEY); store.removeItem(TOKEN_KEY); } catch (_) { /* ignore */ }
  }
}

export function getToken() {
  const { token } = loadSession();
  return token && TOKEN_RE.test(token) ? token : null;
}

export function getSessionUser() {
  return loadSession().user;
}

// Small cookies the backend sets alongside the token flow (trace_lang is readable; trace_device is HttpOnly).
export function readCookie(name) {
  try {
    const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
    return match ? decodeURIComponent(match[1]) : null;
  } catch (_) {
    return null;
  }
}
