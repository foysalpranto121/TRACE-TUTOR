import { createContext, useContext } from 'react';

/**
 * The auth context object and the hook that reads it.
 *
 * Kept apart from AuthProvider so that file exports only a component: a module that
 * mixes components with plain values loses React Fast Refresh, and every edit to the
 * provider then does a full page reload instead of a hot swap.
 */
export const AuthContext = createContext();

export const useAuth = () => useContext(AuthContext);

/** Where each role lands after signing in. */
export const roleHome = (role) =>
  (role === 'EXPERT_TEACHER' ? '/expert' : role === 'RESEARCHER_ADMIN' ? '/admin' : '/dashboard');
