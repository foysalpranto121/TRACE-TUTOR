import { useState, useEffect } from 'react';
import { AuthContext } from './useAuth';
import { apiService } from '../services/api';
import { loadSession, saveSession, updateSessionUser, updateSessionToken, clearSession, getToken, readCookie } from '../services/session';

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
  // Before login / after logout: the language cookie the server set on the last login wins, then
  // whatever the visitor picked as a guest, then Bangla.
  const [guestLanguage, setGuestLanguage] = useState(() => {
    const fromCookie = readCookie('trace_lang');
    if (fromCookie === 'bn' || fromCookie === 'en') return fromCookie;
    try { return localStorage.getItem(GUEST_LANG_KEY) || 'bn'; } catch (_) { return 'bn'; }
  });

  // Validate the stored session against the server once on load; stale or legacy
  // sessions are dropped rather than trusted.
  useEffect(() => {
    if (!validatable) {
      // A user without a token cannot authenticate, so clear the leftovers.
      if (stored.user) clearSession();
      return undefined;
    }
    let cancelled = false;
    apiService.me()
      .then((fresh) => { if (!cancelled) { updateSessionUser(fresh); setUser(fresh); } })
      .catch((err) => { if (!cancelled && err.status === 401) { clearSession(); setUser(null); } })
      .finally(() => { if (!cancelled) setReady(true); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const onExpired = () => setUser(null);
    window.addEventListener('trace:session-expired', onExpired);
    return () => window.removeEventListener('trace:session-expired', onExpired);
  }, []);

  const login = async (identifier, password, remember = true) => {
    const res = await apiService.login(identifier, password);
    saveSession(res.user, res.token, remember);
    setUser(res.user);
    apiService.logTelemetry('LOGIN', { role: res.user.role });
    return res.user;
  };

  const register = async (payload) => {
    const res = await apiService.register(payload);
    saveSession(res.user, res.token, true);
    setUser(res.user);
    apiService.logTelemetry('REGISTER', { role: res.user.role });
    return res.user;
  };

  const logout = () => {
    const token = getToken();
    const pending = user ? apiService.logTelemetry('LOGOUT', { timestamp: new Date().toISOString() }) : Promise.resolve();
    clearSession();
    setUser(null);
    if (token) pending.finally(() => apiService.logout(token).catch(() => {}));
  };

  const updateUser = (patch) => {
    setUser((prev) => {
      if (!prev) return prev;
      const next = { ...prev, ...patch };
      updateSessionUser(next);
      return next;
    });
  };

  const updateProfile = async (patch) => {
    const fresh = await apiService.updateProfile(patch);
    updateSessionUser(fresh);
    setUser(fresh);
    return fresh;
  };

  const uploadAvatar = async (file) => {
    const fresh = await apiService.uploadAvatar(file);
    updateSessionUser(fresh);
    setUser(fresh);
    return fresh;
  };

  const removeAvatar = async () => {
    const fresh = await apiService.deleteAvatar();
    updateSessionUser(fresh);
    setUser(fresh);
    return fresh;
  };

  const changePassword = async (currentPassword, newPassword) => {
    const res = await apiService.changePassword(currentPassword, newPassword);
    if (res.token) updateSessionToken(res.token);
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

  // Tutor mode is self-selectable; persisted so the workspace and the research log agree.
  const setArm = async (newArm) => {
    if (!user || newArm === user.arm) return user;
    const previous = user.arm;
    updateUser({ arm: newArm });
    try {
      return await updateProfile({ assigned_arm: newArm });
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
        uploadAvatar,
        removeAvatar,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

