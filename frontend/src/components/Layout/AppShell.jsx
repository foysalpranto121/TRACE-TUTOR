import { useEffect, useRef, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import {
  Code, LayoutDashboard, FileCheck, Brain, Database, Sliders, Bell, User, Languages, LogOut,
  Sun, Moon, Zap, Flame, ChevronRight, Menu, Sparkles, Repeat, Lock, X,
} from 'lucide-react';
import { useAuth } from '../../context/useAuth';
import { useTheme } from '../../context/useTheme';
import { apiService } from '../../services/api';
import { useResetOnChange } from '../../hooks/useResetOnChange';
import { computeXp, levelInfo } from '../../data/gamification';
import { armLabel } from '../../data/profileOptions';
import { ProgressBar, Avatar } from '../ui';
import { HeaderSearch } from './HeaderSearch';

const NAV = [
  { path: '/dashboard', label: 'ড্যাশবোর্ড', en: 'Dashboard', icon: LayoutDashboard, roles: ['STUDENT', 'EXPERT_TEACHER', 'RESEARCHER_ADMIN'] },
  { path: '/workspace', label: 'কোডিং স্টুডিও', en: 'Workspace', icon: Code, roles: ['STUDENT', 'EXPERT_TEACHER', 'RESEARCHER_ADMIN'] },
  { path: '/assessment', label: 'মূল্যায়ন পরীক্ষা', en: 'Assessments', icon: FileCheck, roles: ['STUDENT', 'RESEARCHER_ADMIN'] },
  { path: '/expert', label: 'শিক্ষক CVI পোর্টাল', en: 'Expert portal', icon: Brain, roles: ['EXPERT_TEACHER', 'RESEARCHER_ADMIN'] },
  { path: '/admin/rag', label: 'RAG ইনস্পেক্টর', en: 'RAG inspector', icon: Database, roles: ['RESEARCHER_ADMIN'] },
  { path: '/admin', label: 'অ্যাডমিন প্যানেল', en: 'Admin analytics', icon: Sliders, roles: ['RESEARCHER_ADMIN'] },
  { path: '/profile', label: 'প্রোফাইল ও সেটিংস', en: 'Profile & settings', icon: User, roles: ['STUDENT', 'EXPERT_TEACHER', 'RESEARCHER_ADMIN'] },
];

const ROLE_BADGE = {
  EXPERT_TEACHER: 'bg-secondary/12 text-secondary border-secondary/30',
  RESEARCHER_ADMIN: 'bg-success/12 text-success border-success/30',
  STUDENT: 'bg-primary/12 text-primary border-primary/30',
};

const TAGLINES = {
  STUDENT: 'ধাপে ধাপে যুক্তি বুঝে প্রোগ্রামিং শিখুন',
  EXPERT_TEACHER: 'NCTB প্রশ্ন ও শিক্ষার্থীর কোড মূল্যায়ন করুন',
  RESEARCHER_ADMIN: 'গবেষণা অ্যানালিটিক্স ও সিস্টেম কন্ট্রোল',
};
const EN_TAGLINES = {
  STUDENT: 'Learn programming step by step',
  EXPERT_TEACHER: 'Review NCTB questions and student code',
  RESEARCHER_ADMIN: 'Research analytics and system controls',
};

export const AppShell = ({ children }) => {
  const { user, role, arm, language, logout, toggleArm, setLanguage } = useAuth();
  const { isDark, toggleTheme } = useTheme();
  const location = useLocation();
  const navigate = useNavigate();
  const [showNotifications, setShowNotifications] = useState(false);
  const [mobileNav, setMobileNav] = useState(false);
  const drawerRef = useRef(null);
  const menuButtonRef = useRef(null);
  const bn = language === 'bn';
  const logoutLabel = bn ? 'লগ আউট' : 'Log out';
  const [progress, setProgress] = useState(null);

  const isStudent = role === 'STUDENT';

  // The sidebar shows live XP so progress is visible from every page, not just the dashboard.
  useEffect(() => {
    if (!isStudent) return undefined;
    let alive = true;
    const load = () => apiService.getDashboard().then((d) => { if (alive) setProgress(d); }).catch(() => {});
    load();
    const id = setInterval(load, 60000);
    return () => { alive = false; clearInterval(id); };
  }, [isStudent, location.pathname]);

  // Navigating closes the mobile drawer before paint, not a frame later.
  useResetOnChange(location.pathname, () => setMobileNav(false));

  useEffect(() => {
    if (!mobileNav) return undefined;
    const drawer = drawerRef.current;
    const opener = menuButtonRef.current;
    const desktop = window.matchMedia('(min-width: 1024px)');
    const closeOnDesktop = () => { if (desktop.matches) setMobileNav(false); };
    // Native modal dialogs contain keyboard focus and make the background inert.
    drawer.showModal();
    drawer.querySelector('button').focus();
    closeOnDesktop();
    desktop.addEventListener('change', closeOnDesktop);
    return () => {
      desktop.removeEventListener('change', closeOnDesktop);
      drawer.close();
      opener?.focus();
    };
  }, [mobileNav]);

  const level = progress ? levelInfo(computeXp(progress.stats, progress.assessments)) : null;
  const streak = progress?.stats?.streak_days || 0;
  const visibleNav = NAV.filter((item) => item.roles.includes(role));
  const displayName = user?.full_name || user?.username || 'User';
  const current = visibleNav.find((n) => n.path === location.pathname);

  const handleLogout = () => { logout(); navigate('/login'); };

  const sidebar = (
    <>
      <div className="px-5 pt-5 pb-4">
        <Link to="/" className="flex items-center gap-2.5 group">
          <div className="w-10 h-10 rounded-xl bg-surface-container p-1.5 border border-primary/30 shadow-glow-sm flex items-center justify-center group-hover:scale-105 transition-transform">
            <img src="/nctb_ict_logo.png" alt="" className="w-full h-full object-contain" />
          </div>
          <div className="leading-tight min-w-0">
            <span className="font-display font-bold text-base block">TRACE Tutor</span>
            <span className="text-[9px] font-mono text-primary font-bold uppercase tracking-[0.14em]">HSC ICT · {bn ? 'বাংলাদেশ' : 'Bangladesh'}</span>
          </div>
        </Link>
      </div>

      {/* Identity + live progression */}
      <div className="px-3.5 pb-3">
        <div className="rounded-2xl bg-surface-container border border-outline-variant/40 p-3.5 space-y-3">
          <div className="flex items-center gap-2.5">
            <Link to="/profile" title={bn ? 'প্রোফাইল ও ছবি বদলান' : 'Edit profile and photo'} className="shrink-0 hover:scale-105 transition-transform">
              <Avatar user={user} size={38} />
            </Link>
            <div className="min-w-0 flex-1">
              <div className="text-xs font-bold truncate">{displayName}</div>
              <div className="text-[10px] font-mono text-on-surface-variant truncate">{user?.participant_code || role}</div>
            </div>
            <span className={`px-1.5 py-0.5 rounded border text-[9px] font-mono font-extrabold shrink-0 ${ROLE_BADGE[role] || ROLE_BADGE.STUDENT}`}>
              {role === 'EXPERT_TEACHER' ? 'TEACHER' : role === 'RESEARCHER_ADMIN' ? 'ADMIN' : 'STUDENT'}
            </span>
          </div>

          {isStudent && level && (
            <div className="space-y-1.5">
              <div className="flex items-center justify-between text-[10px] font-mono">
                <span className="flex items-center gap-1 font-bold text-xp"><Zap className="w-3 h-3" /> Lv.{level.level} {level.title}</span>
                {streak > 0 && (
                  <span className="flex items-center gap-1 font-bold text-streak">
                    <Flame className="w-3 h-3 animate-flame-flicker" />{streak}
                  </span>
                )}
              </div>
              <ProgressBar value={level.progressPct} tone="xp" height="h-1.5" />
              <div className="text-[9px] font-mono text-on-surface-variant">
                {level.next ? `${level.xpForNext} XP → Lv.${level.next.level}` : 'সর্বোচ্চ লেভেল অর্জিত'}
              </div>
            </div>
          )}

          {!isStudent && <p className="text-[10px] text-on-surface-variant leading-relaxed italic">{bn ? TAGLINES[role] : EN_TAGLINES[role]}</p>}

          {/* Tutor mode. Participants may switch it while the study allows self-selection
              (arm_self_select, reported by the server); when a controlled run locks it,
              the pill is shown but not clickable. Staff may always switch. */}
          {isStudent && user?.arm_self_select === false ? (
            <div
              className="w-full flex items-center justify-between px-2.5 py-1.5 rounded-lg bg-surface-container-high border border-outline-variant/40 text-[10px]"
              title={user?.arm_switch_reason === 'after_protocol'
                ? 'চারটি পরীক্ষা শেষ হলে টিউটর মোড বদলাতে পারবেন (you can switch after completing all four papers)'
                : 'আপনার টিউটর মোড গবেষণার জন্য নির্ধারিত (your tutor mode is assigned by the study)'}
            >
              <span className="flex items-center gap-1.5 font-mono font-bold">
                <span className={`w-2 h-2 rounded-full ${arm === 'REASONING_VISIBLE' ? 'bg-success animate-pulse' : 'bg-warning'}`} />
                {armLabel(arm)}
              </span>
              <span className="flex items-center gap-1 text-on-surface-variant font-bold">
                <Lock className="w-3 h-3" />{user?.arm_switch_reason === 'after_protocol' ? 'after tests' : 'assigned'}
              </span>
            </div>
          ) : (
            <button
              onClick={toggleArm}
              className="w-full flex items-center justify-between px-2.5 py-1.5 rounded-lg bg-surface-container-high border border-outline-variant/40 text-[10px] hover:border-primary/40 press"
              title={bn ? `টিউটর মোড: ${armLabel(arm)} — বদলাতে ক্লিক করুন` : `Tutor mode: ${armLabel(arm)} — click to switch`}
            >
              <span className="flex items-center gap-1.5 font-mono font-bold">
                <span className={`w-2 h-2 rounded-full ${arm === 'REASONING_VISIBLE' ? 'bg-success animate-pulse' : 'bg-warning'}`} />
                {armLabel(arm)}
              </span>
              <span className="flex items-center gap-1 text-primary font-bold"><Repeat className="w-3 h-3" />switch</span>
            </button>
          )}
        </div>
      </div>

      <nav className="flex-1 px-3 space-y-1 overflow-y-auto no-scrollbar">
        {visibleNav.map((item) => {
          const Icon = item.icon;
          const active = location.pathname === item.path;
          return (
            <Link
              key={item.path}
              to={item.path}
              className={`group relative flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-semibold transition-all ${
                active ? 'bg-primary/12 text-primary' : 'text-on-surface-variant hover:text-on-surface hover:bg-surface-container-high'
              }`}
            >
              {active && <span className="absolute left-0 top-1/2 -translate-y-1/2 h-6 w-1 rounded-r-full bg-primary" />}
              <Icon className={`w-4 h-4 shrink-0 transition-transform group-hover:scale-110 ${active ? 'text-primary' : ''}`} />
              <span className="min-w-0 leading-tight">
                <span className="block truncate">{bn ? item.label : item.en}</span>
                {bn && <span lang="en" className="block text-[9px] font-mono text-on-surface-variant/80 truncate">{item.en}</span>}
              </span>
              {active && <ChevronRight className="w-3.5 h-3.5 ml-auto shrink-0" />}
            </Link>
          );
        })}
      </nav>

      <div className="px-3.5 pt-3 mt-2 border-t border-outline-variant/30 space-y-2">
        <div className="flex items-center justify-between px-2.5 py-2 rounded-xl bg-surface-container border border-outline-variant/40 text-[11px]">
          <span className="flex items-center gap-1.5 font-semibold text-on-surface-variant"><Languages className="w-3.5 h-3.5 text-primary" /> {bn ? 'ভাষা' : 'Language'}</span>
          <button aria-label={bn ? 'ইংরেজিতে পরিবর্তন করুন' : 'Switch to Bengali'} onClick={() => setLanguage(language === 'bn' ? 'en' : 'bn')} className="px-2 py-0.5 rounded-lg bg-surface-container-high font-mono font-bold text-xs press hover:text-primary">
            {language === 'bn' ? 'বাংলা' : 'EN'}
          </button>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={toggleTheme} className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-xl bg-surface-container border border-outline-variant/40 text-[11px] font-bold press hover:border-primary/40" title={bn ? 'থিম পরিবর্তন করুন' : 'Toggle theme'}>
            {isDark ? <><Sun className="w-3.5 h-3.5 text-warning" /> {bn ? 'হালকা' : 'Soft'}</> : <><Moon className="w-3.5 h-3.5 text-secondary" /> {bn ? 'গাঢ়' : 'Dark'}</>}
          </button>
          <button onClick={handleLogout} className="px-3 py-2 rounded-xl bg-danger/10 text-danger border border-danger/30 press hover:bg-danger/20" aria-label={logoutLabel} title={logoutLabel}>
            <LogOut className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </>
  );

  return (
    <div className="fixed inset-0 overflow-hidden bg-surface text-on-surface flex">
      {/* Desktop sidebar */}
      <aside className="hidden lg:flex w-[268px] h-full bg-surface-container-lowest border-r border-outline-variant/30 flex-col pb-5 shrink-0 z-30">
        {sidebar}
      </aside>

      {/* Mobile drawer */}
      {mobileNav && (
        <dialog ref={drawerRef} id="mobile-navigation" aria-modal="true" aria-label={bn ? 'মূল নেভিগেশন' : 'Main navigation'}
          className="fixed inset-0 m-0 p-0 w-full max-w-none h-full max-h-none border-0 bg-transparent text-on-surface backdrop:bg-black/60"
          onCancel={() => setMobileNav(false)} onClose={() => setMobileNav(false)}
          onClick={(event) => { if (event.target === event.currentTarget) setMobileNav(false); }}>
          <aside className="w-[280px] max-w-full h-full bg-surface-container-lowest border-r border-outline-variant/30 flex flex-col pb-5 overflow-y-auto animate-slide-in">
            <button type="button" onClick={() => setMobileNav(false)} aria-label={bn ? 'মেনু বন্ধ করুন' : 'Close menu'}
              className="self-end shrink-0 m-2 p-2 rounded-xl hover:bg-surface-container-high">
              <X aria-hidden="true" className="w-4 h-4" />
            </button>
            {sidebar}
          </aside>
        </dialog>
      )}

      <div className="flex-1 flex flex-col h-full min-w-0 min-h-0 overflow-hidden">
        <header className="h-16 glass-panel border-x-0 border-t-0 z-20 flex items-center justify-between gap-3 px-3 sm:px-5 shrink-0">
          <button ref={menuButtonRef} onClick={() => setMobileNav(true)} className="lg:hidden p-2 rounded-xl bg-surface-container border border-outline-variant/40" aria-label={bn ? 'মেনু খুলুন' : 'Open menu'} aria-expanded={mobileNav} aria-controls={mobileNav ? 'mobile-navigation' : undefined}>
            <Menu className="w-4 h-4" />
          </button>

          <div className="hidden md:flex items-center gap-2 min-w-0">
            {current && (
              <>
                <current.icon className="w-4 h-4 text-primary shrink-0" />
                <span className="font-display font-bold text-sm truncate">{bn ? current.label : current.en}</span>
                {bn && <span lang="en" className="text-[10px] font-mono text-on-surface-variant hidden xl:inline">/ {current.en}</span>}
              </>
            )}
          </div>

          <HeaderSearch />

          <div className="flex items-center gap-2 shrink-0">
            {isStudent && level && (
              <div className="hidden sm:flex items-center gap-2 px-2.5 py-1.5 rounded-xl bg-surface-container border border-outline-variant/40">
                <Zap className="w-3.5 h-3.5 text-xp" />
                <span className="text-[11px] font-mono font-extrabold">{level.xp.toLocaleString()} XP</span>
                {streak > 0 && <span className="flex items-center gap-0.5 text-[11px] font-mono font-extrabold text-streak border-l border-outline-variant/40 pl-2"><Flame className="w-3.5 h-3.5 animate-flame-flicker" />{streak}</span>}
              </div>
            )}

            <div className="relative">
              <button onClick={() => setShowNotifications(!showNotifications)} className="p-2 rounded-xl bg-surface-container text-on-surface-variant hover:text-on-surface border border-outline-variant/40 press" aria-label={bn ? 'নোটিফিকেশন' : 'Notifications'}>
                <Bell className="w-4 h-4" />
                <span className="absolute top-1.5 right-1.5 w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />
              </button>
              {showNotifications && (
                <div className="absolute right-0 mt-2 w-80 glass-panel rounded-2xl shadow-lift p-3 z-50 space-y-2 animate-scale-in">
                  <h4 className="text-[10px] font-extrabold uppercase tracking-wider text-on-surface-variant px-1">{bn ? 'নোটিফিকেশন' : 'Notifications'}</h4>
                  {isStudent && streak > 0 && (
                    <div className="p-3 rounded-xl bg-streak/10 border border-streak/25 text-xs flex items-start gap-2">
                      <Flame className="w-4 h-4 text-streak shrink-0 mt-0.5" />
                      <span><strong className="text-on-surface">{streak} দিনের স্ট্রিক!</strong> <span className="text-on-surface-variant">আজ অনুশীলন করে ধারাবাহিকতা ধরে রাখুন।</span></span>
                    </div>
                  )}
                  <div className="p-3 rounded-xl bg-surface-container border border-outline-variant/30 text-xs flex items-start gap-2">
                    <Sparkles className="w-4 h-4 text-primary shrink-0 mt-0.5" />
                    <span><strong className="text-on-surface">{bn ? 'RAG কর্পাস সিঙ্ক হয়েছে' : 'RAG corpus synced'}</strong> <span className="text-on-surface-variant">{bn ? '— NCTB অধ্যায় ৪ ও ৫ ইনডেক্স করা আছে।' : '— NCTB chapters 4 and 5 are indexed.'}</span></span>
                  </div>
                </div>
              )}
            </div>

            <button onClick={handleLogout} aria-label={logoutLabel} title={logoutLabel} className="hidden sm:inline-flex px-3 py-2 rounded-xl bg-danger/10 text-danger border border-danger/30 font-bold text-xs items-center gap-1.5 press hover:bg-danger/20">
              <LogOut aria-hidden="true" className="w-3.5 h-3.5" /> <span className="hidden lg:inline">{logoutLabel}</span>
            </button>
          </div>
        </header>

        {/* key on the route so each page fades in - cheap sense of motion between screens */}
        <main key={location.pathname} className="flex-1 min-h-0 p-3 sm:p-4 flex flex-col overflow-y-auto overscroll-contain animate-fade-in">
          {children}
        </main>
      </div>
    </div>
  );
};
