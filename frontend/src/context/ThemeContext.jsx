import { useState, useEffect, useMemo } from 'react';
import { ThemeContext } from './useTheme';

const THEME_KEY = 'trace_theme';
const FX_KEY = 'trace_fx';

// Motion levels for the animated "programming interface" layer.
// full    - code rain, ambient glow, celebrations
// minimal - keep entrances and feedback, drop the decorative loops
// off     - static UI (also forced when the OS asks for reduced motion)

const read = (key, fallback) => {
  try { return localStorage.getItem(key) || fallback; } catch (_) { return fallback; }
};

export const ThemeProvider = ({ children }) => {
  // 'light' was the old pure-white theme; sessions that stored it migrate to the warm 'soft' theme.
  const [theme, setTheme] = useState(() => (read(THEME_KEY, 'dark') === 'dark' ? 'dark' : 'soft'));
  const [fx, setFxState] = useState(() => read(FX_KEY, 'full'));
  const [systemReducedMotion, setSystemReducedMotion] = useState(
    () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
  );

  useEffect(() => {
    const mq = window.matchMedia?.('(prefers-reduced-motion: reduce)');
    if (!mq) return undefined;
    const onChange = (e) => setSystemReducedMotion(e.matches);
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);

  // The OS preference always wins over the stored choice.
  const effectiveFx = systemReducedMotion ? 'off' : fx;

  useEffect(() => {
    const root = document.documentElement;
    root.classList.toggle('dark', theme === 'dark');
    root.classList.toggle('soft', theme !== 'dark');
    root.classList.remove('light');
    try { localStorage.setItem(THEME_KEY, theme); } catch (_) { /* storage blocked */ }
  }, [theme]);

  useEffect(() => {
    document.documentElement.setAttribute('data-fx', effectiveFx);
  }, [effectiveFx]);

  const setFx = (level) => {
    setFxState(level);
    try { localStorage.setItem(FX_KEY, level); } catch (_) { /* storage blocked */ }
  };

  const value = useMemo(() => ({
    theme,
    isDark: theme === 'dark',
    toggleTheme: () => setTheme((p) => (p === 'dark' ? 'soft' : 'dark')),
    setTheme: (t) => setTheme(t === 'dark' ? 'dark' : 'soft'),
    fx: effectiveFx,
    fxChoice: fx,
    setFx,
    systemReducedMotion,
    ambient: effectiveFx === 'full',      // heavy decorative layers (code rain)
    celebrate: effectiveFx !== 'off',     // XP toasts / level-up
  }), [theme, effectiveFx, fx, systemReducedMotion]);

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
};

