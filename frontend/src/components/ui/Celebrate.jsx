import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { Zap, Trophy, Award, CheckCircle2, AlertTriangle, X, Sparkles } from 'lucide-react';
import { useTheme } from '../../context/ThemeContext';

const CelebrateContext = createContext({ toast: () => {}, levelUp: () => {} });
export const useCelebrate = () => useContext(CelebrateContext);

const TONE = {
  xp: { icon: Zap, cls: 'border-xp/40 bg-xp/10 text-xp' },
  badge: { icon: Award, cls: 'border-secondary/40 bg-secondary/10 text-secondary' },
  success: { icon: CheckCircle2, cls: 'border-success/40 bg-success/10 text-success' },
  error: { icon: AlertTriangle, cls: 'border-danger/40 bg-danger/10 text-danger' },
  info: { icon: Sparkles, cls: 'border-primary/40 bg-primary/10 text-primary' },
};

let seq = 0;

export const CelebrateProvider = ({ children }) => {
  const { celebrate, ambient } = useTheme();
  const [toasts, setToasts] = useState([]);
  const [level, setLevel] = useState(null);
  const timers = useRef([]);

  useEffect(() => () => timers.current.forEach(clearTimeout), []);

  const dismiss = useCallback((id) => setToasts((t) => t.filter((x) => x.id !== id)), []);

  const toast = useCallback((opts) => {
    const id = ++seq;
    // Queue stays short so a burst of unlocks can't bury the UI.
    setToasts((t) => [...t.slice(-3), { id, kind: 'info', ttl: 4200, ...opts }]);
    timers.current.push(setTimeout(() => dismiss(id), opts.ttl || 4200));
    return id;
  }, [dismiss]);

  const levelUp = useCallback((info) => {
    setLevel(info);
    timers.current.push(setTimeout(() => setLevel(null), 3600));
  }, []);

  const value = useMemo(() => ({ toast, levelUp, dismiss }), [toast, levelUp, dismiss]);

  return (
    <CelebrateContext.Provider value={value}>
      {children}

      {/* Toast stack */}
      <div className="fixed z-[70] bottom-4 right-4 left-4 sm:left-auto sm:w-[330px] flex flex-col gap-2 pointer-events-none" aria-live="polite">
        {toasts.map((t) => {
          const tone = TONE[t.kind] || TONE.info;
          const Icon = t.icon || tone.icon;
          return (
            <div
              key={t.id}
              className={`pointer-events-auto relative overflow-hidden rounded-2xl border glass-panel shadow-lift p-3.5 flex items-start gap-3 ${celebrate ? 'animate-toast-in' : ''}`}
            >
              <div className={`w-9 h-9 rounded-xl border flex items-center justify-center shrink-0 ${tone.cls}`}>
                <Icon className="w-4.5 h-4.5" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-xs font-extrabold text-on-surface font-display leading-tight">{t.title}</div>
                {t.subtitle && <div className="text-[11px] text-on-surface-variant mt-0.5 leading-snug">{t.subtitle}</div>}
              </div>
              {t.amount != null && (
                <div className={`text-sm font-extrabold font-display shrink-0 ${tone.cls.split(' ').pop()}`}>+{t.amount}</div>
              )}
              <button onClick={() => dismiss(t.id)} className="shrink-0 text-on-surface-variant hover:text-on-surface" aria-label="Dismiss">
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          );
        })}
      </div>

      {/* Level-up takeover */}
      {level && (
        <div className="fixed inset-0 z-[80] flex items-center justify-center pointer-events-none px-4">
          <div className="absolute inset-0 bg-surface/70 backdrop-blur-sm animate-fade-in" />
          <div className="relative text-center animate-pop">
            {ambient && (
              <>
                <span className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-40 h-40 rounded-full border-2 border-xp animate-burst" />
                <span className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-40 h-40 rounded-full border-2 border-primary animate-burst" style={{ animationDelay: '180ms' }} />
                {Array.from({ length: 10 }).map((_, i) => (
                  <span
                    key={i}
                    className="absolute top-0 w-1.5 h-1.5 rounded-sm bg-xp animate-spark-fall"
                    style={{ left: `${8 + i * 9}%`, animationDelay: `${i * 90}ms` }}
                  />
                ))}
              </>
            )}
            <div className="relative bg-surface-container border border-xp/40 rounded-3xl px-8 py-7 shadow-glow">
              <Trophy className="w-10 h-10 text-xp mx-auto mb-2" />
              <div className="text-[11px] font-mono font-bold text-xp uppercase tracking-[0.2em]">Level up!</div>
              <div className="text-4xl font-extrabold font-display mt-1">লেভেল {level.level}</div>
              <div className="text-sm font-bold text-on-surface mt-1">{level.title}</div>
              {level.bn && <div className="text-xs text-on-surface-variant">{level.bn}</div>}
            </div>
          </div>
        </div>
      )}
    </CelebrateContext.Provider>
  );
};

// Floating "+N XP" that rises out of an element - used on the Run button.
export const XpFloat = ({ amount, show }) => {
  const { celebrate } = useTheme();
  if (!show || !celebrate) return null;
  return (
    <span className="absolute -top-1 left-1/2 -translate-x-1/2 text-xs font-extrabold font-display text-xp pointer-events-none animate-rise whitespace-nowrap">
      +{amount} XP
    </span>
  );
};
