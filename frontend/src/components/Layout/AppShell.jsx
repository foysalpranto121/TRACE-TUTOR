import React, { useEffect, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import {
  Code, LayoutDashboard, FileCheck, Brain, Database, Sliders, Search, Bell, User, Languages, LogOut,
  Sun, Moon, Zap, Flame, ChevronRight, Menu, Sparkles, Repeat,
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useTheme } from '../../context/ThemeContext';
import { apiService } from '../../services/api';
import { computeXp, levelInfo } from '../../data/gamification';
import { armLabel } from '../../data/profileOptions';
import { ProgressBar, Badge, Avatar } from '../ui';

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

export const AppShell = ({ children }) => {
  const { user, role, arm, language, logout, toggleArm, setLanguage } = useAuth();
  const { isDark, toggleTheme } = useTheme();
  const location = useLocation();
  const navigate = useNavigate();
  const [showNotifications, setShowNotifications] = useState(false);
  const [mobileNav, setMobileNav] = useState(false);
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

  useEffect(() => { setMobileNav(false); }, [location.pathname]);

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
            <span className="text-[9px] font-mono text-primary font-bold uppercase tracking-[0.14em]">HSC ICT · বাংলাদেশ</span>
          </div>
        </Link>
      </div>

      {/* Identity + live progression */}
      <div className="px-3.5 pb-3">
        <div className="rounded-2xl bg-surface-container border border-outline-variant/40 p-3.5 space-y-3">
          <div className="flex items-center gap-2.5">
            <Link to="/profile" title="প্রোফাইল ও ছবি বদলান" className="shrink-0 hover:scale-105 transition-transform">
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

          {!isStudent && <p className="text-[10px] text-on-surface-variant leading-relaxed italic">{TAGLINES[role]}</p>}

          {/* Tutor mode is self-selectable - one tap swaps the workspace between reasoning and answer-only */}
          <button
            onClick={toggleArm}
            className="w-full flex items-center justify-between px-2.5 py-1.5 rounded-lg bg-surface-container-high border border-outline-variant/40 text-[10px] hover:border-primary/40 press"
            title={`টিউটর মোড: ${armLabel(arm)} — বদলাতে ক্লিক করুন (switch tutor mode)`}
          >
            <span className="flex items-center gap-1.5 font-mono font-bold">
              <span className={`w-2 h-2 rounded-full ${arm === 'REASONING_VISIBLE' ? 'bg-success animate-pulse' : 'bg-warning'}`} />
              {armLabel(arm)}
            </span>
            <span className="flex items-center gap-1 text-primary font-bold"><Repeat className="w-3 h-3" />switch</span>
          </button>
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
                <span className="block truncate">{item.label}</span>
                <span className="block text-[9px] font-mono text-on-surface-variant/80 truncate">{item.en}</span>
              </span>
              {active && <ChevronRight className="w-3.5 h-3.5 ml-auto shrink-0" />}
            </Link>
          );
        })}
      </nav>

      <div className="px-3.5 pt-3 mt-2 border-t border-outline-variant/30 space-y-2">
        <div className="flex items-center justify-between px-2.5 py-2 rounded-xl bg-surface-container border border-outline-variant/40 text-[11px]">
          <span className="flex items-center gap-1.5 font-semibold text-on-surface-variant"><Languages className="w-3.5 h-3.5 text-primary" /> ভাষা</span>
          <button onClick={() => setLanguage(language === 'bn' ? 'en' : 'bn')} className="px-2 py-0.5 rounded-lg bg-surface-container-high font-mono font-bold text-xs press hover:text-primary">
            {language === 'bn' ? 'বাংলা' : 'EN'}
          </button>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={toggleTheme} className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-xl bg-surface-container border border-outline-variant/40 text-[11px] font-bold press hover:border-primary/40" title="Toggle theme">
            {isDark ? <><Sun className="w-3.5 h-3.5 text-warning" /> Soft</> : <><Moon className="w-3.5 h-3.5 text-secondary" /> Dark</>}
          </button>
          <button onClick={handleLogout} className="px-3 py-2 rounded-xl bg-danger/10 text-danger border border-danger/30 press hover:bg-danger/20" title="Log out">
            <LogOut className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </>
  );

  return (
    <div className="h-screen w-screen overflow-hidden bg-surface text-on-surface flex">
      {/* Desktop sidebar */}
      <aside className="hidden lg:flex w-[268px] h-full bg-surface-container-lowest border-r border-outline-variant/30 flex-col pb-5 shrink-0 z-30">
        {sidebar}
      </aside>

      {/* Mobile drawer */}
      {mobileNav && (
        <>
          <div className="lg:hidden fixed inset-0 bg-black/60 z-40 animate-fade-in" onClick={() => setMobileNav(false)} />
          <aside className="lg:hidden fixed inset-y-0 left-0 w-[280px] bg-surface-container-lowest border-r border-outline-variant/30 flex flex-col pb-5 z-50 animate-slide-in">
            {sidebar}
          </aside>
        </>
      )}

      <div className="flex-1 flex flex-col h-full min-w-0 min-h-0 overflow-hidden">
        <header className="h-16 glass-panel border-x-0 border-t-0 z-20 flex items-center justify-between gap-3 px-3 sm:px-5 shrink-0">
          <button onClick={() => setMobileNav(true)} className="lg:hidden p-2 rounded-xl bg-surface-container border border-outline-variant/40" aria-label="Open menu">
            <Menu className="w-4 h-4" />
          </button>

          <div className="hidden md:flex items-center gap-2 min-w-0">
            {current && (
              <>
                <current.icon className="w-4 h-4 text-primary shrink-0" />
                <span className="font-display font-bold text-sm truncate">{current.label}</span>
                <span className="text-[10px] font-mono text-on-surface-variant hidden xl:inline">/ {current.en}</span>
              </>
            )}
          </div>

          <div className="flex-1 md:flex-none md:w-72 flex items-center bg-surface-container rounded-xl px-3 py-2 border border-outline-variant/40 focus-within:border-primary/60 transition-colors">
            <Search className="w-3.5 h-3.5 text-on-surface-variant mr-2 shrink-0" />
            <input type="text" placeholder="টপিক বা টাস্ক খুঁজুন..." className="bg-transparent border-none outline-none text-xs w-full placeholder:text-outline" />
          </div>

          <div className="flex items-center gap-2 shrink-0">
            {isStudent && level && (
              <div className="hidden sm:flex items-center gap-2 px-2.5 py-1.5 rounded-xl bg-surface-container border border-outline-variant/40">
                <Zap className="w-3.5 h-3.5 text-xp" />
                <span className="text-[11px] font-mono font-extrabold">{level.xp.toLocaleString()} XP</span>
                {streak > 0 && <span className="flex items-center gap-0.5 text-[11px] font-mono font-extrabold text-streak border-l border-outline-variant/40 pl-2"><Flame className="w-3.5 h-3.5 animate-flame-flicker" />{streak}</span>}
              </div>
            )}

            <div className="relative">
              <button onClick={() => setShowNotifications(!showNotifications)} className="p-2 rounded-xl bg-surface-container text-on-surface-variant hover:text-on-surface border border-outline-variant/40 press" aria-label="Notifications">
                <Bell className="w-4 h-4" />
                <span className="absolute top-1.5 right-1.5 w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />
              </button>
              {showNotifications && (
                <div className="absolute right-0 mt-2 w-80 glass-panel rounded-2xl shadow-lift p-3 z-50 space-y-2 animate-scale-in">
                  <h4 className="text-[10px] font-extrabold uppercase tracking-wider text-on-surface-variant px-1">নোটিফিকেশন</h4>
                  {isStudent && streak > 0 && (
                    <div className="p-3 rounded-xl bg-streak/10 border border-streak/25 text-xs flex items-start gap-2">
                      <Flame className="w-4 h-4 text-streak shrink-0 mt-0.5" />
                      <span><strong className="text-on-surface">{streak} দিনের স্ট্রিক!</strong> <span className="text-on-surface-variant">আজ অনুশীলন করে ধারাবাহিকতা ধরে রাখুন।</span></span>
                    </div>
                  )}
                  <div className="p-3 rounded-xl bg-surface-container border border-outline-variant/30 text-xs flex items-start gap-2">
                    <Sparkles className="w-4 h-4 text-primary shrink-0 mt-0.5" />
                    <span><strong className="text-on-surface">RAG কর্পাস সিঙ্ক হয়েছে</strong> <span className="text-on-surface-variant">— NCTB অধ্যায় ৪ ও ৫ ইনডেক্স করা আছে।</span></span>
                  </div>
                </div>
              )}
            </div>

            <button onClick={handleLogout} className="hidden sm:inline-flex px-3 py-2 rounded-xl bg-danger/10 text-danger border border-danger/30 font-bold text-xs items-center gap-1.5 press hover:bg-danger/20">
              <LogOut className="w-3.5 h-3.5" /> <span className="hidden lg:inline">লগ আউট</span>
            </button>
          </div>
        </header>

        {/* key on the route so each page fades in - cheap sense of motion between screens */}
        <main key={location.pathname} className="flex-1 min-h-0 p-3 sm:p-4 flex flex-col overflow-y-auto animate-fade-in">
          {children}
        </main>
      </div>
    </div>
  );
};
