import { useState, useEffect, useRef } from 'react';
import { AuthContext } from './useAuth';
import { apiService } from '../services/api';
import { loadSession, saveSession, updateSessionUser, updateSessionToken, clearSession, getToken, readCookie } from '../services/session';
import { createProfileRefresh } from '../services/profileRefresh';

const GUEST_LANG_KEY = 'trace_lang';

export const AuthProvider = ({ children }) => {
  // Read the stored session once. A session is only worth validating if it has both a
  // user and a token; anything else is stale and the app is ready immediately.
  const [stored] = useState(() => ({ user: loadSession().user, token: getToken() }));
  const validatable = Boolean(stored.user && stored.token);

  const [user, setUser] = useState(validatable ? stored.user : null);
  // Starting from the derived value means the "nothing to validate" path needs no
  // synchronous setState inside the effect below.
  const [ready, setReady] = useState(!validatable);
  const userRef = useRef(validatable ? stored.user : null);
  const validated = useRef(false);
  const authAttempt = useRef(0);
  const readIdentity = () => {
    const current = userRef.current;
    const session = loadSession();
    const token = getToken();
    return current && session.user?.id === current.id && token ? { id: current.id, token } : null;
  };
  const sameIdentity = (identity) => {
    const current = readIdentity();
    return identity && current && identity.id === current.id && identity.token === current.token;
  };
  const commitUser = (next) => {
    userRef.current = next;
    if (next) updateSessionUser(next);
    setUser(next);
  };
  const profileRefresh = useRef(null);
  // Before login / after logout: the language cookie the server set on the last login wins, then
  // whatever the visitor picked as a guest, then Bangla.
  const [guestLanguage, setGuestLanguage] = useState(() => {
    const fromCookie = readCookie('trace_lang');
    if (fromCookie === 'bn' || fromCookie === 'en') return fromCookie;
    try { return localStorage.getItem(GUEST_LANG_KEY) || 'bn'; } catch (_) { return 'bn'; }
  });

  // Refresh server-owned mode permissions after submissions in this tab or another
  // tab, and when returning to the app. Incomplete participants stay locked until
  // the server explicitly reports otherwise.
  useEffect(() => {
    let cancelled = false;
    const controller = createProfileRefresh({
      readIdentity,
      fetchProfile: () => apiService.me(),
      applyProfile: (fresh) => {
        // Refresh server-owned permissions without overwriting edits in this tab.
        if (validated.current && ['arm_self_select', 'arm_switch_reason', 'arm_switch_policy']
          .every((key) => userRef.current?.[key] === fresh[key])) return;
        const next = validated.current ? { ...userRef.current,
          arm_self_select: fresh.arm_self_select, arm_switch_reason: fresh.arm_switch_reason,
          arm_switch_policy: fresh.arm_switch_policy } : fresh;
        validated.current = true;
        commitUser(next);
      },
      expireSession: () => { authAttempt.current++; clearSession(); commitUser(null); setReady(true); },
    });
    profileRefresh.current = controller;
    controller.start();
    if (!validatable && stored.user) clearSession();
    controller.refresh({ invalidate: true })
      .finally(() => { if (!cancelled) setReady(true); });
    const refresh = () => controller.refresh({ invalidate: true });
    const visible = () => { if (document.visibilityState !== 'hidden') refresh(); };
    const storage = (event) => { if (event.key === 'trace:assessment-changed') refresh(); };
    const onExpired = () => {
      profileRefresh.current?.invalidate();
      authAttempt.current++;
      clearSession();
      commitUser(null);
      setReady(true);
    };
    window.addEventListener('trace:assessment-changed', refresh);
    window.addEventListener('storage', storage);
    window.addEventListener('focus', visible);
    document.addEventListener('visibilitychange', visible);
    window.addEventListener('trace:session-expired', onExpired);
    return () => {
      cancelled = true;
      controller.stop();
      if (profileRefresh.current === controller) profileRefresh.current = null;
      window.removeEventListener('trace:assessment-changed', refresh);
      window.removeEventListener('storage', storage);
      window.removeEventListener('focus', visible);
      document.removeEventListener('visibilitychange', visible);
      window.removeEventListener('trace:session-expired', onExpired);
    };
    // The controller reads current session refs rather than render-time user state.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profileRefresh]);

  useEffect(() => {
    document.documentElement.lang = user?.language || guestLanguage;
  }, [user?.language, guestLanguage]);

  const login = async (identifier, password, remember = true) => {
    const attempt = ++authAttempt.current;
    profileRefresh.current?.invalidate();
    const res = await apiService.login(identifier, password);
    if (attempt !== authAttempt.current) return res.user;
    saveSession(res.user, res.token, remember);
    validated.current = true;
    commitUser(res.user);
    setReady(true);
    apiService.logTelemetry('LOGIN', { role: res.user.role });
    return res.user;
  };

  const register = async (payload) => {
    const attempt = ++authAttempt.current;
    profileRefresh.current?.invalidate();
    const res = await apiService.register(payload);
    if (attempt !== authAttempt.current) return res.user;
    saveSession(res.user, res.token, true);
    validated.current = true;
    commitUser(res.user);
    setReady(true);
    apiService.logTelemetry('REGISTER', { role: res.user.role });
    return res.user;
  };

  const logout = () => {
    authAttempt.current++;
    profileRefresh.current?.invalidate();
    const token = getToken();
    const pending = user ? apiService.logTelemetry('LOGOUT', { timestamp: new Date().toISOString() }) : Promise.resolve();
    clearSession();
    commitUser(null);
    setReady(true);
    if (token) pending.finally(() => apiService.logout(token).catch(() => {}));
  };

  const updateUser = (patch) => {
    profileRefresh.current?.invalidate();
    if (!userRef.current) return;
    validated.current = true;
    commitUser({ ...userRef.current, ...patch });
  };

  const applyProfileMutation = async (request) => {
    profileRefresh.current?.invalidate();
    const identity = readIdentity();
    const fresh = await request();
    if (sameIdentity(identity)) {
      profileRefresh.current?.invalidate();
      validated.current = true;
      commitUser(fresh);
    }
    return fresh;
  };

  const updateProfile = (patch) => applyProfileMutation(() => apiService.updateProfile(patch));
  const uploadAvatar = (file) => applyProfileMutation(() => apiService.uploadAvatar(file));
  const removeAvatar = () => applyProfileMutation(() => apiService.deleteAvatar());

  const changePassword = async (currentPassword, newPassword) => {
    profileRefresh.current?.invalidate();
    const identity = readIdentity();
    const res = await apiService.changePassword(currentPassword, newPassword);
    if (res.token && sameIdentity(identity)) updateSessionToken(res.token);
    return res;
  };

  // Withdraw from the study. The server erases the participant's data and revokes the
  // token in the same request, so once this resolves the person is signed out here too.
  const withdraw = async (password) => {
    const identity = readIdentity();
    const res = await apiService.withdraw(password);
    if (sameIdentity(identity)) {
      authAttempt.current++;
      profileRefresh.current?.invalidate();
      clearSession();
      commitUser(null);
      setReady(true);
    }
    return res;
  };

  const setLanguage = (lang) => {
    if (user) {
      updateUser({ language: lang });
      if (getToken()) apiService.updateProfile({ preferred_language: lang }).catch(() => {});
    } else {
      setGuestLanguage(lang);
      try { localStorage.setItem(GUEST_LANG_KEY, lang); } catch (_) { /* ignore */ }
    }
  };

  // Switch tutor mode. The server decides whether this account may (arm_self_select);
  // an optional reason is stored with the switch for the preference analysis.
  const setArm = async (newArm, reason = '') => {
    if (!user || newArm === user.arm) return user;
    const previous = user.arm;
    updateUser({ arm: newArm });
    try {
      return await updateProfile({ assigned_arm: newArm, ...(reason ? { arm_switch_reason: reason } : {}) });
    } catch (err) {
      updateUser({ arm: previous });
      throw err;
    }
  };

  const toggleArm = () => setArm(user?.arm === 'REASONING_VISIBLE' ? 'ANSWER_ONLY' : 'REASONING_VISIBLE').catch(() => {});

  return (
    <AuthContext.Provider
      value={{
        user,
        ready,
        isAuthenticated: !!user,
        role: user?.role || null,
        arm: user?.arm || 'REASONING_VISIBLE',
        language: user?.language || guestLanguage,
        login,
        register,
        logout,
        toggleArm,
        setArm,
        setLanguage,
        updateProfile,
        updateUser,
        changePassword,
        withdraw,
        uploadAvatar,
        removeAvatar,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

