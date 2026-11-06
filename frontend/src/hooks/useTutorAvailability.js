import { useEffect, useMemo, useSyncExternalStore } from 'react';
import { apiService } from '../services/api';
import { createTutorAvailability } from '../services/tutorAvailability';

export function useTutorAvailability(userId, onDashboard) {
  const store = useMemo(() => createTutorAvailability(() => userId
    ? apiService.getDashboard() : Promise.reject(new Error('Sign in to check tutor availability.')), onDashboard), [userId, onDashboard]);
  const availability = useSyncExternalStore(store.subscribe, store.getSnapshot);
  useEffect(() => {
    store.refresh();
    const refresh = () => { if (document.visibilityState !== 'hidden') store.invalidate(); };
    // Focus and polling refresh quietly after the initial authoritative check.
    const backgroundRefresh = () => { if (document.visibilityState !== 'hidden') store.invalidate({ background: true }); };
    const onStorage = (event) => { if (event.key === 'trace:assessment-changed') refresh(); };
    window.addEventListener('focus', backgroundRefresh);
    document.addEventListener('visibilitychange', backgroundRefresh);
    window.addEventListener('trace:assessment-changed', refresh);
    window.addEventListener('storage', onStorage);
    const timer = setInterval(backgroundRefresh, 30000);
    return () => {
      clearInterval(timer);
      window.removeEventListener('focus', backgroundRefresh);
      document.removeEventListener('visibilitychange', backgroundRefresh);
      window.removeEventListener('trace:assessment-changed', refresh);
      window.removeEventListener('storage', onStorage);
    };
  }, [store]);
  return { availability, refreshAvailability: async () => { await store.refresh(); return store.getSnapshot(); }, reportLocked: store.reportLocked };
}
