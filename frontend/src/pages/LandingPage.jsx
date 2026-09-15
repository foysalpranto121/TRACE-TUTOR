import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowRight, Brain, Code2, Sun, Moon, Sparkles, Play, Terminal, ShieldCheck, Flame, Trophy, Zap,
  BookOpen, CheckCircle2, Bot, Languages, Target, Rocket, Layers, GraduationCap, Menu, X,
} from 'lucide-react';
import { useAuth, roleHome } from '../context/useAuth';
import { useTheme } from '../context/useTheme';
import { prefersReducedMotion } from '../hooks/usePrefersReducedMotion';
import { Button, Badge, Reveal, CountUp } from '../components/ui';
import { CodeRain } from '../components/ui/CodeRain';

const TYPED_LINES = [
  { text: '#include <stdio.h>', cls: 'text-secondary' },
  { text: '', cls: '' },
  { text: 'int main() {', cls: 'text-on-surface' },
  { text: '    int n, sum = 0;', cls: 'text-on-surface-variant' },
  { text: '    scanf("%d", &n);', cls: 'text-on-surface-variant' },
  { text: '    for (int i = 1; i <= n; i++)', cls: 'text-primary' },
  { text: '        sum += i;', cls: 'text-primary' },
  { text: '    printf("Sum = %d", sum);', cls: 'text-on-surface-variant' },
  { text: '    return 0;', cls: 'text-on-surface-variant' },
  { text: '}', cls: 'text-on-surface' },
];

// Each block owns a hue; `--chip` drives the .icon-chip / .tint-card colour system.
const hue = (name) => ({ '--chip': `var(--accent-${name})` });

const FEATURES = [
  {
    icon: Brain, color: 'violet',
    title: 'AI যা যুক্তি দেখায়', en: 'An AI that shows its thinking',
    body: 'শুধু উত্তর নয় — ধাপে ধাপে লজিক, ভুলের কারণ আর NCTB বইয়ের পৃষ্ঠা নম্বরসহ ব্যাখ্যা।',
  },
  {
    icon: Terminal, color: 'sky',
    title: 'সত্যিকারের কম্পাইলার', en: 'A real compiler, not a simulation',
    body: 'আপনার C কোড সত্যিই কম্পাইল ও রান হয়। ভুল লাইনে লাল দাগ, টেস্ট কেস পাস/ফেল — VS Code-এর মতো।',
  },
  {
    icon: Code2, color: 'emerald',
    title: 'HTML লাইভ প্রিভিউ', en: 'Live HTML preview & validation',
    body: 'অধ্যায় ৪-এর টেবিল, লিংক, লিস্ট লিখুন — সঙ্গে সঙ্গে রেন্ডার দেখুন আর ট্যাগের ভুল ধরুন।',
  },
  {
    icon: Trophy, color: 'amber',
    title: 'XP, স্ট্রিক ও ব্যাজ', en: 'XP, streaks and badges',
    body: 'প্রতিটি সমাধানে XP, প্রতিদিন অনুশীলনে স্ট্রিক, আর দক্ষতা অনুযায়ী ব্যাজ আনলক করুন।',
  },
  {
    icon: BookOpen, color: 'teal',
    title: 'NCTB বই থেকেই উত্তর', en: 'Grounded in the NCTB textbook',
    body: 'বাংলা ও ইংরেজি সংস্করণের পাঠ্যবই থেকে হুবহু অনুচ্ছেদ ও পৃষ্ঠা উদ্ধৃতিসহ উত্তর।',
  },
  {
    icon: Target, color: 'rose',
    title: 'বোর্ড পরীক্ষার প্রস্তুতি', en: 'Built for the HSC board exam',
    body: 'প্রি-টেস্ট, পোস্ট-টেস্ট ও ট্রান্সফার টাস্ক — নিজের অগ্রগতি সংখ্যায় দেখুন।',
  },
];

const STEPS = [
  { n: '০১', icon: GraduationCap, color: 'rose', title: 'অ্যাকাউন্ট খুলুন', en: 'Create your account', body: 'কলেজ, শ্রেণি ও অভিজ্ঞতা জানান — ৩০ সেকেন্ডেই শেষ।' },
  { n: '০২', icon: Code2, color: 'sky', title: 'কোড লিখুন ও রান করুন', en: 'Write and run real code', body: 'অধ্যায় ৪ ও ৫-এর টাস্কে কোড লিখুন, টেস্ট কেস পাস করান।' },
  { n: '০৩', icon: Bot, color: 'violet', title: 'AI-কে প্রশ্ন করুন', en: 'Ask the AI tutor', body: 'আটকে গেলে বাংলায় প্রশ্ন করুন — যুক্তিসহ ব্যাখ্যা পাবেন।' },
  { n: '০৪', icon: Trophy, color: 'amber', title: 'অগ্রগতি ট্র্যাক করুন', en: 'Track your progress', body: 'XP, স্ট্রিক, দক্ষতা চার্ট আর পরীক্ষার স্কোর এক ড্যাশবোর্ডে।' },
];

const TOPICS = [
  { chapter: 'অধ্যায় ৪', en: 'Chapter 4', title: 'ওয়েব ডিজাইন ও HTML', icon: Code2, count: '৩টি টাস্ক', tags: ['Table', 'rowspan', 'Hyperlink', 'List', 'Form'], color: 'sky' },
  { chapter: 'অধ্যায় ৫', en: 'Chapter 5', title: 'প্রোগ্রামিং ভাষা (C)', icon: Terminal, count: '৫টি টাস্ক', tags: ['Loop', 'if-else', 'Factorial', 'Prime', 'Array'], color: 'violet' },
  { chapter: 'অধ্যায় ৬', en: 'Chapter 6', title: 'ডেটাবেজ ও SQL', icon: Layers, count: 'MCQ', tags: ['Primary Key', 'SELECT', 'WHERE', 'Relation'], color: 'emerald' },
];

const useTypewriter = (lines, speed = 22) => {
  const [typedCount, setTypedCount] = useState(0);
  const full = lines.map((l) => l.text).join('\n');
  // Reduced motion shows the finished text straight away, derived rather than set
  // from an effect - otherwise the first paint is empty and then snaps to full.
  const reduced = prefersReducedMotion();
  const count = reduced ? full.length : typedCount;
  useEffect(() => {
    if (reduced) return undefined;
    const id = setInterval(() => setTypedCount((c) => (c >= full.length ? c : c + 1)), speed);
    return () => clearInterval(id);
  }, [full, speed, reduced]);
  const shown = full.slice(0, count).split('\n');
  return lines.map((l, i) => ({ ...l, shown: shown[i] ?? '', active: shown.length - 1 === i && count < full.length }));
};

export const LandingPage = () => {
  const { isDark, toggleTheme } = useTheme();
  const { user } = useAuth();
  const typed = useTypewriter(TYPED_LINES);
  const [menuOpen, setMenuOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 12);
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  const primaryCta = user ? { to: roleHome(user.role), label: 'ড্যাশবোর্ডে যান (Go to dashboard)' } : { to: '/register', label: 'বিনামূল্যে শুরু করুন' };

  return (
    <div className="min-h-screen bg-surface text-on-surface overflow-x-hidden">
      {/* ── Nav ─────────────────────────────────────────────────────────── */}
      <header className={`sticky top-0 z-50 transition-all duration-300 ${scrolled ? 'glass-panel border-x-0 border-t-0 shadow-lift' : 'border-b border-transparent'}`}>
        <nav className="max-w-7xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between gap-4">
          <Link to="/" className="flex items-center gap-2.5 group shrink-0">
            <div className="w-10 h-10 rounded-xl bg-surface-container p-1.5 border border-primary/30 shadow-glow-sm flex items-center justify-center group-hover:scale-105 transition-transform">
              <img src="/nctb_ict_logo.png" alt="" className="w-full h-full object-contain" />
            </div>
            <div className="leading-tight">
              <span className="font-display font-bold text-base block">TRACE Tutor</span>
              <span className="text-[9px] font-mono text-primary font-bold uppercase tracking-[0.15em]">HSC ICT · বাংলাদেশ</span>
            </div>
          </Link>

          <div className="hidden md:flex items-center gap-1 text-xs font-semibold text-on-surface-variant">
            <a href="#features" className="px-3 py-2 rounded-lg hover:text-on-surface hover:bg-surface-container-high transition-colors">ফিচার</a>
            <a href="#how" className="px-3 py-2 rounded-lg hover:text-on-surface hover:bg-surface-container-high transition-colors">কীভাবে কাজ করে</a>
            <a href="#topics" className="px-3 py-2 rounded-lg hover:text-on-surface hover:bg-surface-container-high transition-colors">সিলেবাস</a>
          </div>

          <div className="flex items-center gap-2">
            <button onClick={toggleTheme} className="p-2 rounded-xl bg-surface-container border border-outline-variant/40 text-on-surface-variant hover:text-on-surface press" title="Toggle theme" aria-label="Toggle theme">
              {isDark ? <Sun className="w-4 h-4 text-warning" /> : <Moon className="w-4 h-4 text-secondary" />}
            </button>
            <Link to="/login" className="hidden sm:inline-flex px-4 py-2 rounded-xl bg-surface-container border border-outline-variant/40 text-on-surface font-bold text-xs press hover:border-primary/40">
              লগইন
            </Link>
            <Button as={Link} to={primaryCta.to} size="sm" className="hidden sm:inline-flex btn-vivid">
              {user ? 'ড্যাশবোর্ড' : 'শুরু করুন'} <ArrowRight className="w-3.5 h-3.5" />
            </Button>
            <button onClick={() => setMenuOpen(!menuOpen)} className="md:hidden p-2 rounded-xl bg-surface-container border border-outline-variant/40" aria-label="Menu">
              {menuOpen ? <X className="w-4 h-4" /> : <Menu className="w-4 h-4" />}
            </button>
          </div>
        </nav>
        {menuOpen && (
          <div className="md:hidden glass-panel border-x-0 px-4 py-3 space-y-2 animate-fade-up">
            {[['#features', 'ফিচার'], ['#how', 'কীভাবে কাজ করে'], ['#topics', 'সিলেবাস']].map(([href, label]) => (
              <a key={href} href={href} onClick={() => setMenuOpen(false)} className="block px-3 py-2 rounded-lg text-sm font-semibold hover:bg-surface-container-high">{label}</a>
            ))}
            <div className="flex gap-2 pt-1">
              <Link to="/login" className="flex-1 text-center px-4 py-2.5 rounded-xl bg-surface-container-high border border-outline-variant/40 font-bold text-xs">লগইন</Link>
              <Button as={Link} to={primaryCta.to} size="md" className="flex-1">শুরু করুন</Button>
            </div>
          </div>
        )}
      </header>

      {/* ── Hero ────────────────────────────────────────────────────────── */}
      <section className="relative bg-grid overflow-hidden">
        <CodeRain density={0.85} opacity={0.75} />
        <div className="absolute inset-0 pointer-events-none overflow-hidden" aria-hidden>
          <div className="absolute -top-40 -left-32 w-[520px] h-[520px] rounded-full bg-accent-sky/25 blur-[130px]" />
          <div className="absolute -top-20 left-1/3 w-[380px] h-[380px] rounded-full bg-accent-rose/20 blur-[120px]" />
          <div className="absolute top-10 right-0 w-[460px] h-[460px] rounded-full bg-accent-violet/25 blur-[130px]" />
          <div className="absolute bottom-10 left-1/4 w-[360px] h-[360px] rounded-full bg-accent-amber/20 blur-[120px]" />
          <div className="absolute inset-x-0 bottom-0 h-40 bg-gradient-to-b from-transparent to-surface" />
        </div>

        <div className="relative max-w-7xl mx-auto px-4 sm:px-6 pt-14 pb-20 grid lg:grid-cols-2 gap-12 items-center">
          <div className="space-y-6">
            <div style={hue('rose')} className="chip-soft inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-[11px] font-extrabold animate-fade-up">
              <Sparkles className="w-3.5 h-3.5" /> এইচএসসি আইসিটি · অধ্যায় ৪, ৫ ও ৬
            </div>

            <h1 className="text-4xl sm:text-5xl xl:text-6xl font-extrabold leading-[1.08] animate-fade-up stagger-1">
              মুখস্থ নয় —<br />
              <span className="text-gradient">যুক্তি বুঝে</span><br />
              প্রোগ্রামিং শিখুন
            </h1>

            <p className="text-base text-on-surface-variant leading-relaxed max-w-xl animate-fade-up stagger-2">
              এমন একটা AI টিউটর যে শুধু উত্তর দেয় না — <strong className="text-on-surface font-semibold">প্রতিটা ধাপের যুক্তি দেখায়</strong>, NCTB পাঠ্যবইয়ের পৃষ্ঠা থেকে উদ্ধৃতি দেয়, আর আপনার কোড সত্যিকারের কম্পাইলারে চালিয়ে ভুলটা ঠিক কোন লাইনে তা ধরিয়ে দেয়।
            </p>

            <div className="flex flex-wrap items-center gap-3 animate-fade-up stagger-3">
              <Button as={Link} to={primaryCta.to} size="lg" className="btn-vivid">
                <Rocket className="w-4 h-4" /> {primaryCta.label} <ArrowRight className="w-4 h-4" />
              </Button>
              <Button as={Link} to="/login" variant="surface" size="lg">
                <Play className="w-4 h-4 text-primary" /> আগে থেকেই অ্যাকাউন্ট আছে
              </Button>
            </div>

            <div className="flex flex-wrap items-center gap-2 pt-2 animate-fade-up stagger-4">
              {[
                { icon: CheckCircle2, label: 'সম্পূর্ণ বিনামূল্যে', color: 'emerald' },
                { icon: Languages, label: 'বাংলা ও ইংরেজি', color: 'sky' },
                { icon: ShieldCheck, label: 'গবেষণা-অনুমোদিত', color: 'violet' },
              ].map((c) => (
                <span key={c.label} style={hue(c.color)} className="chip-soft inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold">
                  <c.icon className="w-3.5 h-3.5" /> {c.label}
                </span>
              ))}
            </div>
          </div>

          {/* Live-typing editor mock */}
          <div className="relative animate-scale-in stagger-2">
            <div className="absolute -inset-4 bg-gradient-to-tr from-primary/20 via-secondary/10 to-transparent blur-2xl rounded-3xl" aria-hidden />
            <div className="relative rounded-2xl border border-outline-variant/50 bg-surface-container-lowest shadow-lift overflow-hidden">
              <div className="flex items-center gap-2 px-4 py-2.5 bg-surface-container-high border-b border-outline-variant/40">
                <span className="flex gap-1.5" aria-hidden>
                  <span className="w-2.5 h-2.5 rounded-full bg-danger/70" />
                  <span className="w-2.5 h-2.5 rounded-full bg-warning/70" />
                  <span className="w-2.5 h-2.5 rounded-full bg-success/70" />
                </span>
                <span className="text-[11px] font-mono text-on-surface-variant ml-1">main.c</span>
                <Badge tone="success" className="ml-auto"><span className="w-1.5 h-1.5 rounded-full bg-success animate-pulse" /> Compiler ready</Badge>
              </div>

              <pre className="p-4 text-[12px] leading-[1.75] font-mono overflow-x-auto min-h-[248px]">
                {typed.map((line, i) => (
                  <div key={i} className="flex">
                    <span className="w-7 shrink-0 text-outline select-none text-right pr-3">{i + 1}</span>
                    <code className={`${line.cls} ${line.active ? 'caret' : ''}`}>{line.shown || ' '}</code>
                  </div>
                ))}
              </pre>

              <div className="border-t border-outline-variant/40 bg-surface-container-high px-4 py-3 space-y-2">
                <div className="flex items-center gap-2 text-[11px] font-mono">
                  <CheckCircle2 className="w-3.5 h-3.5 text-success" />
                  <span className="text-success font-bold">2/2 test cases passed</span>
                  <span className="text-on-surface-variant ml-auto">14 ms</span>
                </div>
                <div className="flex items-start gap-2 rounded-lg bg-secondary/10 border border-secondary/25 p-2.5">
                  <Bot className="w-3.5 h-3.5 text-secondary shrink-0 mt-0.5" />
                  <p className="text-[11px] text-on-surface leading-relaxed">
                    <span className="font-bold text-secondary">TRACE:</span> লুপের শর্ত <code className="font-mono text-primary">i &lt;= n</code> রাখলে N সংখ্যাটিও যোগ হবে।
                    <span className="text-on-surface-variant"> [NCTB (BV) p.১৪৬]</span>
                  </p>
                </div>
              </div>
            </div>

            <div className="absolute -bottom-5 -left-5 hidden sm:flex items-center gap-2 px-3 py-2 rounded-xl glass-panel shadow-lift animate-float">
              <Flame className="w-4 h-4 text-streak animate-flame-flicker" />
              <div className="leading-none">
                <div className="text-sm font-extrabold font-display">৭ দিন</div>
                <div className="text-[9px] font-mono text-on-surface-variant uppercase">streak</div>
              </div>
            </div>
            <div className="absolute -bottom-5 -right-4 hidden sm:flex items-center gap-2 px-3 py-2 rounded-xl glass-panel shadow-lift animate-float" style={{ animationDelay: '1.2s' }}>
              <Zap className="w-4 h-4 text-xp" />
              <div className="leading-none">
                <div className="text-sm font-extrabold font-display">+১০০ XP</div>
                <div className="text-[9px] font-mono text-on-surface-variant uppercase">task solved</div>
              </div>
            </div>
          </div>
        </div>

        {/* Stat strip */}
        <div className="relative max-w-7xl mx-auto px-4 sm:px-6 pb-14">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            {[
              { icon: Layers, value: 8, suffix: '+', label: 'প্র্যাকটিস টাস্ক', color: 'sky' },
              { icon: BookOpen, value: 60, suffix: '+', label: 'পরীক্ষার প্রশ্ন', color: 'violet' },
              { icon: Terminal, value: 4, suffix: '', label: 'ভাষা সাপোর্ট', color: 'emerald' },
              { icon: ShieldCheck, value: 100, suffix: '%', label: 'পাঠ্যবই-ভিত্তিক', color: 'amber' },
            ].map((s, i) => (
              <Reveal key={s.label} delay={i * 70}>
                <div style={hue(s.color)} className="tint-card rounded-2xl border p-4 card-interactive h-full">
                  <div className="icon-chip w-10 h-10 rounded-xl flex items-center justify-center mb-2.5"><s.icon className="w-5 h-5" /></div>
                  <div className="text-2xl font-extrabold font-display"><CountUp value={s.value} />{s.suffix}</div>
                  <div className="text-[11px] text-on-surface-variant font-semibold">{s.label}</div>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* ── Features ────────────────────────────────────────────────────── */}
      <section id="features" className="max-w-7xl mx-auto px-4 sm:px-6 py-20 scroll-mt-20">
        <Reveal className="text-center max-w-2xl mx-auto space-y-3 mb-12">
          <span style={hue('violet')} className="chip-soft inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[11px] font-extrabold"><Sparkles className="w-3 h-3" /> কেন TRACE Tutor</span>
          <h2 className="text-3xl sm:text-4xl font-extrabold">অন্য AI উত্তর দেয়।<br /><span className="text-gradient">TRACE শেখায়।</span></h2>
          <p className="text-sm text-on-surface-variant leading-relaxed">
            কপি-পেস্ট করে পরীক্ষায় পাস করা যায় না। তাই প্রতিটা উত্তরের সঙ্গে যুক্তি, পাঠ্যবইয়ের রেফারেন্স আর সত্যিকারের কম্পাইলার ফিডব্যাক।
          </p>
        </Reveal>

        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {FEATURES.map((f, i) => (
            <Reveal key={f.en} delay={i * 60}>
              <article style={hue(f.color)} className="group h-full tint-card rounded-2xl border p-5 card-interactive">
                <div className="icon-chip w-12 h-12 rounded-2xl flex items-center justify-center mb-4 group-hover:scale-110 group-hover:-rotate-6 transition-transform">
                  <f.icon className="w-6 h-6" />
                </div>
                <h3 className="text-base font-bold mb-0.5">{f.title}</h3>
                <p className="text-[11px] font-mono text-on-surface-variant mb-2.5">{f.en}</p>
                <p className="text-xs text-on-surface-variant leading-relaxed">{f.body}</p>
              </article>
            </Reveal>
          ))}
        </div>
      </section>

      {/* ── How it works ────────────────────────────────────────────────── */}
      <section id="how" className="relative py-20 scroll-mt-20 bg-surface-container-lowest border-y border-outline-variant/30">
        <div className="max-w-7xl mx-auto px-4 sm:px-6">
          <Reveal className="text-center max-w-2xl mx-auto space-y-3 mb-12">
            <span style={hue('orange')} className="chip-soft inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[11px] font-extrabold"><Rocket className="w-3 h-3" /> শুরু করা সহজ</span>
            <h2 className="text-3xl sm:text-4xl font-extrabold">৪ ধাপে শুরু</h2>
          </Reveal>

          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {STEPS.map((s, i) => (
              <Reveal key={s.n} delay={i * 80}>
                <div style={hue(s.color)} className="group relative h-full tint-card rounded-2xl border p-5 card-interactive">
                  <span className="absolute top-3 right-4 text-4xl font-extrabold font-display opacity-15 select-none" style={{ color: 'rgb(var(--chip))' }}>{s.n}</span>
                  <div className="icon-chip w-12 h-12 rounded-2xl flex items-center justify-center mb-4 group-hover:scale-110 transition-transform"><s.icon className="w-6 h-6" /></div>
                  <h3 className="text-base font-bold mb-0.5">{s.title}</h3>
                  <p className="text-[11px] font-mono text-on-surface-variant mb-2">{s.en}</p>
                  <p className="text-xs text-on-surface-variant leading-relaxed">{s.body}</p>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* ── Syllabus ────────────────────────────────────────────────────── */}
      <section id="topics" className="max-w-7xl mx-auto px-4 sm:px-6 py-20 scroll-mt-20">
        <Reveal className="text-center max-w-2xl mx-auto space-y-3 mb-12">
          <span style={hue('emerald')} className="chip-soft inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[11px] font-extrabold"><BookOpen className="w-3 h-3" /> এনসিটিবি সিলেবাস</span>
          <h2 className="text-3xl sm:text-4xl font-extrabold">যা যা শিখবেন</h2>
          <p className="text-sm text-on-surface-variant">বোর্ড বইয়ের অধ্যায় ধরে ধরে — প্রতিটা টপিকে অনুশীলন, টেস্ট কেস আর AI ব্যাখ্যা।</p>
        </Reveal>

        <div className="grid md:grid-cols-3 gap-4">
          {TOPICS.map((t, i) => (
            <Reveal key={t.en} delay={i * 80}>
              <div style={hue(t.color)} className="group h-full tint-card rounded-2xl border p-6 card-interactive">
                <div className="flex items-center gap-3 mb-4">
                  <div className="icon-chip w-12 h-12 rounded-2xl flex items-center justify-center shrink-0 group-hover:scale-110 transition-transform">
                    <t.icon className="w-6 h-6" />
                  </div>
                  <div className="min-w-0">
                    <div className="chip-soft inline-flex px-2 py-0.5 rounded-full text-[10px] font-mono font-extrabold">{t.chapter}</div>
                    <div className="text-[10px] font-mono text-on-surface-variant mt-0.5">{t.en} · {t.count}</div>
                  </div>
                </div>
                <h3 className="text-lg font-bold mb-3">{t.title}</h3>
                <div className="flex flex-wrap gap-1.5">
                  {t.tags.map((tag) => (
                    <span key={tag} className="chip-soft px-2 py-1 rounded-lg text-[10px] font-mono font-bold">{tag}</span>
                  ))}
                </div>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* ── Final CTA ───────────────────────────────────────────────────── */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 pb-24">
        <Reveal>
          <div className="relative rounded-3xl border border-primary/30 bg-surface-container overflow-hidden p-8 sm:p-14 text-center">
            <div className="absolute inset-0 bg-grid opacity-60" aria-hidden />
            <div className="absolute -top-24 left-1/4 w-96 h-96 rounded-full bg-primary/20 blur-[120px]" aria-hidden />
            <div className="absolute -bottom-24 right-1/4 w-96 h-96 rounded-full bg-secondary/20 blur-[120px]" aria-hidden />
            <div className="relative space-y-5">
              <h2 className="text-3xl sm:text-4xl font-extrabold max-w-2xl mx-auto leading-tight">
                আজই প্রথম প্রোগ্রামটা <span className="text-gradient">রান করে ফেলুন</span>
              </h2>
              <p className="text-sm text-on-surface-variant max-w-lg mx-auto">
                কোনো ইনস্টল লাগবে না, কোনো খরচ নেই। শুধু একটা অ্যাকাউন্ট খুলুন আর ব্রাউজারেই কোডিং শুরু করুন।
              </p>
              <div className="flex flex-wrap items-center justify-center gap-3 pt-2">
                <Button as={Link} to={primaryCta.to} size="lg" className="btn-vivid">
                  <Rocket className="w-4 h-4" /> {primaryCta.label} <ArrowRight className="w-4 h-4" />
                </Button>
                <Button as={Link} to="/login" variant="surface" size="lg">লগইন করুন</Button>
              </div>
            </div>
          </div>
        </Reveal>
      </section>

      {/* ── Footer ──────────────────────────────────────────────────────── */}
      <footer className="border-t border-outline-variant/30 py-8">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 flex flex-wrap items-center justify-between gap-4 text-[11px] font-mono text-on-surface-variant">
          <div className="flex items-center gap-2.5">
            <img src="/nctb_ict_logo.png" alt="" className="w-7 h-7 object-contain" />
            <span>© ২০২৬ TRACE Tutor · NCTB HSC ICT Research Platform</span>
          </div>
          <div className="flex items-center gap-4">
            <span>Consent v1</span>
            <Link to="/login" className="hover:text-primary transition-colors">লগইন</Link>
            <Link to="/register" className="hover:text-primary transition-colors">নিবন্ধন</Link>
          </div>
        </div>
      </footer>
    </div>
  );
};
