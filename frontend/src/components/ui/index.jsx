import { useEffect, useRef, useState } from 'react';
import { prefersReducedMotion } from '../../hooks/usePrefersReducedMotion';

// ---------------------------------------------------------------- primitives
const VARIANTS = {
  primary: 'bg-primary text-on-primary shadow-glow-sm hover:brightness-110 sheen',
  secondary: 'bg-secondary text-on-secondary hover:brightness-110',
  surface: 'bg-surface-container-high text-on-surface border border-outline-variant/50 hover:bg-surface-container-highest hover:border-primary/40',
  ghost: 'text-on-surface-variant hover:text-on-surface hover:bg-surface-container-high',
  danger: 'bg-danger/10 text-danger border border-danger/30 hover:bg-danger/20',
};
const SIZES = { sm: 'px-3 py-1.5 text-xs gap-1.5', md: 'px-4 py-2.5 text-xs gap-2', lg: 'px-6 py-3.5 text-sm gap-2.5' };

export const Button = ({ as: Tag = 'button', variant = 'primary', size = 'md', className = '', children, ...props }) => (
  <Tag
    className={`inline-flex items-center justify-center rounded-xl font-bold press disabled:opacity-50 disabled:pointer-events-none ${VARIANTS[variant]} ${SIZES[size]} ${className}`}
    {...props}
  >
    {children}
  </Tag>
);

export const Card = ({ interactive = false, className = '', children, ...props }) => (
  <div
    className={`bg-surface-container rounded-2xl border border-outline-variant/40 shadow-lift ${interactive ? 'card-interactive' : ''} ${className}`}
    {...props}
  >
    {children}
  </div>
);

export const SectionCard = ({ icon, title, subtitle, action, className = '', bodyClass = 'p-5', children }) => (
  <Card className={`flex flex-col overflow-hidden ${className}`}>
    <header className="px-5 py-3.5 border-b border-outline-variant/30 flex items-center justify-between gap-3">
      <div className="min-w-0">
        <h3 className="text-xs font-extrabold text-on-surface uppercase tracking-wider flex items-center gap-2 font-display">{icon}{title}</h3>
        {subtitle && <p className="text-[11px] text-on-surface-variant mt-0.5">{subtitle}</p>}
      </div>
      {action}
    </header>
    <div className={`flex-1 min-h-0 ${bodyClass}`}>{children}</div>
  </Card>
);

const TONES = {
  primary: 'bg-primary/12 text-primary border-primary/30',
  secondary: 'bg-secondary/12 text-secondary border-secondary/30',
  success: 'bg-success/12 text-success border-success/30',
  warning: 'bg-warning/12 text-warning border-warning/30',
  danger: 'bg-danger/12 text-danger border-danger/30',
  neutral: 'bg-surface-container-high text-on-surface-variant border-outline-variant/50',
  xp: 'bg-xp/12 text-xp border-xp/30',
};

export const Badge = ({ tone = 'primary', className = '', children, ...props }) => (
  <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border text-[10px] font-mono font-extrabold ${TONES[tone]} ${className}`} {...props}>
    {children}
  </span>
);

export const ProgressBar = ({ value = 0, tone = 'primary', className = '', height = 'h-2' }) => {
  const tint = { primary: 'bg-primary', success: 'bg-success', xp: 'bg-xp', warning: 'bg-warning', secondary: 'bg-secondary' }[tone];
  return (
    <div className={`${height} w-full rounded-full bg-surface-container-highest overflow-hidden ${className}`} role="progressbar" aria-valuenow={Math.round(value)} aria-valuemin={0} aria-valuemax={100}>
      <div className={`h-full rounded-full ${tint} transition-[width] duration-700 ease-out`} style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
    </div>
  );
};

export const ProgressRing = ({ value = 0, size = 72, stroke = 7, tone = 'rgb(var(--primary))', children }) => {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgb(var(--surface-container-highest))" strokeWidth={stroke} />
        <circle
          cx={size / 2} cy={size / 2} r={r} fill="none" stroke={tone} strokeWidth={stroke} strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={c - (Math.max(0, Math.min(100, value)) / 100) * c}
          style={{ transition: 'stroke-dashoffset .9s cubic-bezier(.22,1,.36,1)' }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">{children}</div>
    </div>
  );
};

// Counts up when it first scrolls into view - makes numbers feel earned.
export const CountUp = ({ value = 0, duration = 900, className = '' }) => {
  const [animated, setAnimated] = useState(0);
  const target = Number(value) || 0;
  // Derived, not stored: a viewer who asked for reduced motion sees the final number
  // immediately instead of one animated frame followed by a correction.
  const reduced = prefersReducedMotion();
  const shown = reduced ? target : animated;
  useEffect(() => {
    if (reduced) return undefined;
    let raf;
    const start = performance.now();
    const tick = (now) => {
      const t = Math.min(1, (now - start) / duration);
      setAnimated(Math.round(target * (1 - Math.pow(1 - t, 3))));
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, duration, reduced]);
  return <span className={className}>{shown.toLocaleString()}</span>;
};

// `color` uses the vivid category palette (solid chip in light, glow tint in dark);
// `tone` keeps the older semantic styling for tiles that carry state meaning.
export const StatTile = ({ icon, label, value, hint, tone = 'primary', color, delay = 0, animate = true }) => (
  <div
    className={`rounded-2xl border shadow-lift p-4 flex items-start gap-3 card-interactive animate-fade-up ${color ? 'tint-card' : 'bg-surface-container border-outline-variant/40'}`}
    style={{ animationDelay: `${delay}ms`, ...(color ? { '--chip': `var(--accent-${color})` } : {}) }}
  >
    <div className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 ${color ? 'icon-chip' : `border ${TONES[tone]}`}`}>{icon}</div>
    <div className="min-w-0">
      <div className="text-[10px] font-mono font-bold text-on-surface-variant uppercase tracking-wider truncate">{label}</div>
      <div className="text-2xl font-extrabold text-on-surface leading-tight font-display">
        {animate && typeof value === 'number' ? <CountUp value={value} /> : value}
      </div>
      {hint && <div className="text-[11px] text-on-surface-variant mt-0.5 truncate">{hint}</div>}
    </div>
  </div>
);

export const Skeleton = ({ className = '' }) => <div className={`skeleton rounded-xl ${className}`} />;

export const EmptyState = ({ icon, title, children, action }) => (
  <div className="text-center py-8 px-4 space-y-2">
    {icon && <div className="w-12 h-12 rounded-2xl bg-surface-container-high border border-outline-variant/40 text-on-surface-variant flex items-center justify-center mx-auto">{icon}</div>}
    <div className="text-sm font-bold text-on-surface font-display">{title}</div>
    {children && <p className="text-xs text-on-surface-variant max-w-sm mx-auto leading-relaxed">{children}</p>}
    {action && <div className="pt-2">{action}</div>}
  </div>
);

// Reveals children with a fade-up the first time they enter the viewport.
export const Reveal = ({ delay = 0, className = '', children }) => {
  const ref = useRef(null);
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const node = ref.current;
    if (!node) return undefined;
    const io = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) { setVisible(true); io.disconnect(); } },
      { threshold: 0.12, rootMargin: '0px 0px -60px 0px' }
    );
    io.observe(node);
    return () => io.disconnect();
  }, []);
  return (
    <div ref={ref} className={`${visible ? 'animate-fade-up' : 'opacity-0'} ${className}`} style={{ animationDelay: `${delay}ms` }}>
      {children}
    </div>
  );
};


// Profile picture with an initials fallback. Sizes are px; `ring` adds the brand halo used in headers.
export const Avatar = ({ user, size = 40, ring = false, className = '' }) => {
  const name = user?.full_name || user?.username || '?';
  const initials = name.split(' ').map((w) => w[0]).filter(Boolean).slice(0, 2).join('').toUpperCase();
  const base = `rounded-2xl overflow-hidden shrink-0 flex items-center justify-center font-extrabold font-display select-none ${ring ? 'ring-2 ring-primary/40 shadow-glow-sm' : ''} ${className}`;
  if (user?.avatar_url) {
    return <img src={user.avatar_url} alt={name} width={size} height={size} className={`${base} object-cover bg-surface-container-high`} style={{ width: size, height: size }} />;
  }
  return (
    <div className={`${base} bg-primary/15 border border-primary/30 text-primary`} style={{ width: size, height: size, fontSize: Math.max(11, size * 0.36) }} aria-label={name}>
      {initials || '?'}
    </div>
  );
};
