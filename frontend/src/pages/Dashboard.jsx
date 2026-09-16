import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import {
  Flame, CheckCircle2, XCircle, Bot, Copy, FileCheck, Sliders, Play, ArrowRight, TrendingUp,
  Database, Sparkles, RefreshCw, AlertTriangle, Code2, Trophy, Activity, LogIn, Users, Brain, ShieldCheck,
  Zap, Target, Crown, Repeat, Lock, Rocket, Award, Clock,
} from 'lucide-react';
import { useAuth } from '../context/useAuth';
import { useTheme } from '../context/useTheme';
import { apiService } from '../services/api';
import { NCTB_PROBLEMS, PROBLEM_BY_ID, SKILLS } from '../data/problems';
import { computeXp, levelInfo, evaluateBadges, DAILY_GOAL_RUNS } from '../data/gamification';
import { armLabel } from '../data/profileOptions';
import { Card, SectionCard, Badge, Button, ProgressBar, ProgressRing, StatTile, CountUp, EmptyState, Skeleton, Avatar } from '../components/ui';

// Two categorical hues (code runs / AI help), validated for CVD separation and contrast per theme surface.
const CHART_COLORS = { dark: { runs: '#22d3ee', help: '#a78bfa' }, soft: { runs: '#0f766e', help: '#6d28d9' } };
const DIFFICULTY_RANK = { Novice: 0, Intermediate: 1, Advanced: 2 };
const EXAM_LABELS = {
  pre: { en: 'Pre-Test (Baseline)', bn: 'প্রি-টেস্ট' },
  post: { en: 'Post-Test (+AI)', bn: 'পোস্ট-টেস্ট' },
  transfer: { en: 'Transfer Test (+AI)', bn: 'ট্রান্সফার টেস্ট' },
  withdrawal: { en: 'Withdrawal Task (No AI)', bn: 'উইথড্রয়াল টাস্ক' },
};
const BADGE_ICONS = { Play, CheckCircle2, Bot, Flame, Zap, Repeat, Code2, FileCheck, Trophy, Target, Crown, Sparkles };

function timeAgo(iso) {
  if (!iso) return '';
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return 'এইমাত্র';
  if (diff < 3600) return `${Math.floor(diff / 60)} মিনিট আগে`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} ঘণ্টা আগে`;
  if (diff < 172800) return 'গতকাল';
  return new Date(iso).toLocaleDateString([], { day: '2-digit', month: 'short' });
}

function greeting() {
  const h = new Date().getHours();
  if (h < 12) return 'শুভ সকাল';
  if (h < 17) return 'শুভ অপরাহ্ন';
  return 'শুভ সন্ধ্যা';
}

const EVENT_ICON = {
  CODE_RESULT: (s) => (s === 'SUCCESS' ? <CheckCircle2 className="w-3.5 h-3.5 text-success" /> : <XCircle className="w-3.5 h-3.5 text-danger" />),
  HELP_REQUEST: () => <Bot className="w-3.5 h-3.5 text-secondary" />,
  COPY_PASTE: () => <Copy className="w-3.5 h-3.5 text-warning" />,
  SUBMIT_ASSESSMENT: () => <FileCheck className="w-3.5 h-3.5 text-primary" />,
  ARM_TOGGLE_MANUAL: () => <Sliders className="w-3.5 h-3.5 text-on-surface-variant" />,
  REGISTER: () => <Sparkles className="w-3.5 h-3.5 text-primary" />,
  LOGIN: () => <LogIn className="w-3.5 h-3.5 text-on-surface-variant" />,
  LOGOUT: () => <LogIn className="w-3.5 h-3.5 text-on-surface-variant" />,
};

const ChartTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-surface-container-high border border-outline-variant/50 rounded-xl px-3 py-2 text-[11px] shadow-lift">
      <div className="font-bold text-on-surface mb-1">{label}</div>
      {payload.map((p) => (
        <div key={p.dataKey} className="flex items-center gap-2 text-on-surface-variant">
          <span className="w-2 h-2 rounded-sm" style={{ background: p.color }} />
          <span>{p.name}</span>
          <span className="ml-auto font-mono font-bold text-on-surface">{p.value}</span>
        </div>
      ))}
    </div>
  );
};

export const Dashboard = () => {
  const { user, role, arm, language } = useAuth();
  const { isDark } = useTheme();
  const [data, setData] = useState(null);
  const [rag, setRag] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  // Bumping this re-runs the fetch effect. The Refresh button is an event handler, so
  // it may set `loading` synchronously; the effect itself must not.
  const [reloadToken, setReloadToken] = useState(0);

  const reload = () => {
    setLoading(true);
    setReloadToken((n) => n + 1);
  };

  // The fetch lives in the effect so nothing is written to state before the first
  // await, and `alive` drops a response that arrives after the participant navigates
  // away instead of setting state on an unmounted component.
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const [d, r] = await Promise.all([
          apiService.getDashboard(),
          apiService.getRagStatus().catch(() => null),
        ]);
        if (!alive) return;
        setData(d);
        setRag(r);
        setError(null);
      } catch (err) {
        if (alive) setError(err.message);
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, [user?.id, reloadToken]);

  const derived = useMemo(() => {
    const progressById = Object.fromEntries((data?.problems || []).map((p) => [p.problem_id, p]));
    const solvedIds = new Set((data?.problems || []).filter((p) => p.solved).map((p) => p.problem_id));
    const attempted = (data?.problems || []).filter((p) => p.attempts > 0 || p.help_requests > 0);
    const byRecency = [...attempted].sort((a, b) => (b.last_at || '').localeCompare(a.last_at || ''));
    const lastUnsolved = byRecency.find((p) => !p.solved && PROBLEM_BY_ID[p.problem_id]);
    const unsolved = NCTB_PROBLEMS.filter((p) => !solvedIds.has(p.id));
    const continueProblem = (lastUnsolved && PROBLEM_BY_ID[lastUnsolved.problem_id]) || unsolved[0] || null;
    const lastSkill = byRecency[0] ? PROBLEM_BY_ID[byRecency[0].problem_id]?.skill : null;

    const recommended = unsolved
      .filter((p) => p.id !== continueProblem?.id)
      .sort((a, b) => {
        const sameSkill = (b.skill === lastSkill) - (a.skill === lastSkill);
        if (sameSkill) return sameSkill;
        return DIFFICULTY_RANK[a.difficulty.split(' ')[0]] - DIFFICULTY_RANK[b.difficulty.split(' ')[0]];
      })
      .slice(0, 3);

    const mastery = SKILLS.map((skill) => {
      const items = NCTB_PROBLEMS.filter((p) => p.skill === skill);
      const score = items.reduce((acc, p) => {
        const prog = progressById[p.id];
        if (!prog) return acc;
        if (prog.solved) return acc + 100;
        if (prog.attempts > 0) return acc + (prog.total_tests ? Math.round((prog.best_passed / prog.total_tests) * 70) : 40);
        return acc + (prog.help_requests > 0 ? 15 : 0);
      }, 0);
      return { skill, pct: Math.round(score / items.length), total: items.length, solved: items.filter((p) => solvedIds.has(p.id)).length };
    }).sort((a, b) => b.pct - a.pct);

    const bestAssessment = Object.values(data?.assessments || {}).reduce((m, a) => Math.max(m, a.best_score || 0), 0);
    const todayKey = new Date().toISOString().slice(0, 10);
    const today = (data?.daily || []).find((d) => d.date === todayKey) || { code_runs: 0, help_requests: 0, solved: 0 };
    const badges = evaluateBadges(data);
    const xp = computeXp(data?.stats || {}, data?.assessments || {});

    return {
      progressById, solvedIds, continueProblem, recommended, mastery, bestAssessment, lastUnsolved,
      hasAssessments: Object.keys(data?.assessments || {}).length > 0,
      today, badges, earned: badges.filter((b) => b.earned), level: levelInfo(xp),
    };
  }, [data]);

  const stats = data?.stats || {};
  const colors = CHART_COLORS[isDark ? 'dark' : 'soft'];
  const isStaff = role === 'EXPERT_TEACHER' || role === 'RESEARCHER_ADMIN';
  const overallPct = Math.round(((stats.problems_solved || 0) / NCTB_PROBLEMS.length) * 100);
  const chartHasData = (data?.daily || []).some((d) => d.code_runs || d.help_requests);
  const bn = language === 'bn';
  const goalPct = Math.min(100, Math.round((derived.today.code_runs / DAILY_GOAL_RUNS) * 100));

  if (loading && !data) {
    return (
      <div className="max-w-7xl mx-auto w-full space-y-4">
        <Skeleton className="h-28" />
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-24" />)}</div>
        <div className="grid lg:grid-cols-12 gap-4"><Skeleton className="h-72 lg:col-span-7" /><Skeleton className="h-72 lg:col-span-5" /></div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto w-full space-y-4 pb-10">
      {/* ── Hero: identity, level, streak, daily goal ─────────────────── */}
      <Card className="relative overflow-hidden p-5 animate-fade-up">
        <div className="absolute inset-0 bg-grid opacity-50 pointer-events-none" aria-hidden />
        <div className="absolute -top-24 -right-16 w-72 h-72 rounded-full bg-primary/10 blur-[90px] pointer-events-none" aria-hidden />
        <div className="relative space-y-4">
          <div className="flex items-center gap-4">
            {!isStaff ? (
              <div
                className="shrink-0"
                title={derived.level.next ? `Level ${derived.level.level} · ${derived.level.xpForNext} XP → Lv.${derived.level.next.level}` : `Level ${derived.level.level} · সর্বোচ্চ লেভেল`}
                aria-label={`Level ${derived.level.level}`}
              >
                <ProgressRing value={derived.level.progressPct} size={84} stroke={6}>
                  <Avatar user={user} size={58} className="!rounded-full" />
                  <span className="absolute -bottom-1 px-1.5 py-0.5 rounded-full bg-surface-container border border-xp/40 text-[9px] font-mono font-extrabold text-xp leading-none">Lv.{derived.level.level}</span>
                </ProgressRing>
              </div>
            ) : (
              <Avatar user={user} size={72} ring />
            )}

            <div className="min-w-0 flex-1">
              <div className="text-[10px] font-mono font-bold text-primary uppercase tracking-wider truncate">
                {isStaff ? 'Research overview' : derived.level.title}
              </div>
              <h1 className="text-lg sm:text-2xl font-extrabold font-display leading-tight">
                {greeting()}, {user?.full_name || user?.username}
              </h1>
              <div className="flex flex-wrap items-center gap-1.5 mt-1.5">
                <Badge tone="primary">{role}</Badge>
                {user?.participant_code && <Badge tone="neutral">{user.participant_code}</Badge>}
                <Link to="/profile" title="টিউটর মোড বদলান (change tutor mode)" className="hidden sm:inline-flex">
                  <Badge tone={arm === 'REASONING_VISIBLE' ? 'success' : 'warning'} className="hover:brightness-125">
                    {armLabel(arm)}
                  </Badge>
                </Link>
                {user?.school_name && <span className="hidden md:inline text-[11px] text-on-surface-variant truncate max-w-[220px]">{user.school_name}</span>}
              </div>
            </div>

            {!isStaff && (
              <div className="hidden sm:flex items-center gap-2.5 shrink-0">
                <div className="px-3.5 py-2.5 rounded-2xl bg-xp/10 border border-xp/30 text-center min-w-[86px]">
                  <div className="flex items-center justify-center gap-1 text-xp"><Zap className="w-3.5 h-3.5" /><span className="text-lg font-extrabold font-display"><CountUp value={derived.level.xp} /></span></div>
                  <div className="text-[9px] font-mono text-on-surface-variant uppercase">total xp</div>
                </div>
                <div className={`px-3.5 py-2.5 rounded-2xl border text-center min-w-[86px] ${stats.streak_days ? 'bg-streak/10 border-streak/30' : 'bg-surface-container-high border-outline-variant/40'}`}>
                  <div className={`flex items-center justify-center gap-1 ${stats.streak_days ? 'text-streak' : 'text-on-surface-variant'}`}>
                    <Flame className={`w-3.5 h-3.5 ${stats.streak_days ? 'animate-flame-flicker' : ''}`} />
                    <span className="text-lg font-extrabold font-display">{stats.streak_days || 0}</span>
                  </div>
                  <div className="text-[9px] font-mono text-on-surface-variant uppercase">day streak</div>
                </div>
              </div>
            )}
          </div>

          {/* XP + streak move to their own row on phones */}
          {!isStaff && (
            <div className="grid grid-cols-2 gap-2 sm:hidden">
              <div className="px-3 py-2 rounded-xl bg-xp/10 border border-xp/30 flex items-center justify-center gap-1.5 text-xp">
                <Zap className="w-4 h-4" /><span className="text-base font-extrabold font-display"><CountUp value={derived.level.xp} /></span>
                <span className="text-[9px] font-mono text-on-surface-variant uppercase">xp</span>
              </div>
              <div className={`px-3 py-2 rounded-xl border flex items-center justify-center gap-1.5 ${stats.streak_days ? 'bg-streak/10 border-streak/30 text-streak' : 'bg-surface-container-high border-outline-variant/40 text-on-surface-variant'}`}>
                <Flame className={`w-4 h-4 ${stats.streak_days ? 'animate-flame-flicker' : ''}`} />
                <span className="text-base font-extrabold font-display">{stats.streak_days || 0}</span>
                <span className="text-[9px] font-mono text-on-surface-variant uppercase">day streak</span>
              </div>
            </div>
          )}

          <div className="flex flex-wrap items-center gap-2">
            {derived.continueProblem && !isStaff && (
              <Button as={Link} to={`/workspace?problem=${derived.continueProblem.id}`} size="md" className="shadow-glow flex-1 sm:flex-none">
                <Play className="w-3.5 h-3.5 fill-current" /> {derived.lastUnsolved ? 'চালিয়ে যান' : 'নতুন টাস্ক শুরু'}
              </Button>
            )}
            <Button as={Link} to="/workspace" variant="surface" size="md"><Code2 className="w-3.5 h-3.5 text-primary" /> Workspace</Button>
            {!isStaff && <Button as={Link} to="/assessment" variant="surface" size="md"><FileCheck className="w-3.5 h-3.5 text-primary" /> পরীক্ষা</Button>}
            <button onClick={reload} className="p-2.5 rounded-xl bg-surface-container-high border border-outline-variant/40 text-on-surface-variant press hover:text-primary ml-auto" title="Refresh">
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>

        {/* Daily goal bar */}
        {!isStaff && (
          <div className="relative mt-4 pt-4 border-t border-outline-variant/30 flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2 text-xs font-bold shrink-0">
              <Target className={`w-4 h-4 ${goalPct >= 100 ? 'text-success' : 'text-primary'}`} />
              আজকের লক্ষ্য
            </div>
            <div className="flex-1 min-w-[160px]"><ProgressBar value={goalPct} tone={goalPct >= 100 ? 'success' : 'primary'} /></div>
            <div className="text-[11px] font-mono text-on-surface-variant shrink-0">
              {goalPct >= 100
                ? <span className="text-success font-bold flex items-center gap-1"><CheckCircle2 className="w-3.5 h-3.5" /> সম্পন্ন! দারুণ কাজ</span>
                : `${derived.today.code_runs}/${DAILY_GOAL_RUNS} কোড রান`}
            </div>
          </div>
        )}
      </Card>

      {error && (
        <div className="bg-danger/10 border border-danger/30 rounded-xl p-4 text-xs text-danger flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0" /> ড্যাশবোর্ড লোড করা যায়নি: {error}
        </div>
      )}

      {/* ── Staff overview ─────────────────────────────────────────────── */}
      {data && isStaff && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <StatTile icon={<Users className="w-5 h-5" />} label="Participants" value={data.overview.participants} hint={`${data.overview.students} students`} color="sky" delay={0} />
            <StatTile icon={<ShieldCheck className="w-5 h-5" />} label="Arm split" value={`${data.overview.arms.REASONING_VISIBLE || 0} / ${data.overview.arms.ANSWER_ONLY || 0}`} hint="Reasoning / Answer-only" color="emerald" delay={60} animate={false} />
            <StatTile icon={<FileCheck className="w-5 h-5" />} label="Submissions" value={data.overview.submissions} hint={`${data.overview.expert_grades} expert grades`} color="violet" delay={120} />
            <StatTile icon={<Activity className="w-5 h-5" />} label="Telemetry events" value={data.overview.events} hint={`${data.overview.active_today} active today`} color="amber" delay={180} />
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
            <StatTile icon={<Code2 className="w-5 h-5" />} label="Code runs" value={data.overview.code_runs} delay={0} />
            <StatTile icon={<Bot className="w-5 h-5" />} label="AI help requests" value={data.overview.help_requests} tone="secondary" delay={60} />
            <StatTile icon={<Database className="w-5 h-5" />} label="RAG index" value={rag ? rag.engine.vector_count : '—'} hint={rag ? `${rag.engine.llm_model} · ${rag.ingest.running ? 'ingesting' : rag.ingest.stage}` : 'status unavailable'} tone="primary" delay={120} animate={false} />
          </div>
          <div className="flex flex-wrap gap-2">
            <Button as={Link} to="/expert" variant="surface"><Brain className="w-4 h-4 text-primary" /> Expert CVI Portal</Button>
            {role === 'RESEARCHER_ADMIN' && <Button as={Link} to="/admin" variant="surface"><Sliders className="w-4 h-4 text-primary" /> Admin Analytics</Button>}
            {role === 'RESEARCHER_ADMIN' && <Button as={Link} to="/admin/rag" variant="surface"><Database className="w-4 h-4 text-primary" /> RAG Inspector</Button>}
          </div>
        </>
      )}

      {/* ── Student dashboard ──────────────────────────────────────────── */}
      {data && !isStaff && (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <StatTile icon={<CheckCircle2 className="w-5 h-5" />} label="সমাধান হয়েছে" value={`${stats.problems_solved || 0}/${NCTB_PROBLEMS.length}`} hint={`${overallPct}% সম্পন্ন · ${stats.problems_attempted || 0} চেষ্টা`} color="emerald" delay={0} animate={false} />
            <StatTile icon={<Award className="w-5 h-5" />} label="ব্যাজ অর্জিত" value={`${derived.earned.length}/${derived.badges.length}`} hint={derived.earned.length ? derived.earned[derived.earned.length - 1].title : 'প্রথম ব্যাজ অপেক্ষা করছে'} color="violet" delay={60} animate={false} />
            <StatTile icon={<Trophy className="w-5 h-5" />} label="সেরা স্কোর" value={derived.hasAssessments ? `${derived.bestAssessment}%` : '—'} hint={derived.hasAssessments ? `${Object.keys(data.assessments).length}/4 পরীক্ষা দেওয়া` : 'এখনো পরীক্ষা দেননি'} color="amber" delay={120} animate={false} />
            <StatTile icon={<Bot className="w-5 h-5" />} label="AI প্রশ্ন" value={stats.help_requests || 0} hint={`${stats.code_runs || 0} রান · ${stats.copy_paste || 0} কপি`} color="sky" delay={180} />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
            <div className="lg:col-span-7 space-y-4">
              {/* Continue learning */}
              <SectionCard icon={<Rocket className="w-4 h-4 text-primary" />} title="যেখানে ছিলেন" subtitle="Continue learning" className="animate-fade-up stagger-1">
                {derived.continueProblem ? (
                  <div className="space-y-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge tone="primary">{derived.continueProblem.skill}</Badge>
                      <Badge tone="neutral">{derived.continueProblem.difficulty}</Badge>
                      <span className="text-[11px] font-mono text-on-surface-variant flex items-center gap-1"><Clock className="w-3 h-3" /> ~{derived.continueProblem.estimated_min} মিনিট</span>
                    </div>
                    <h4 className="text-base font-bold font-display">{derived.continueProblem.title}</h4>
                    <p className="text-xs text-on-surface-variant leading-relaxed">
                      {bn ? derived.continueProblem.description_bn : derived.continueProblem.description_en}
                    </p>
                    {derived.progressById[derived.continueProblem.id] && (
                      <div className="flex flex-wrap gap-2 text-[10px] font-mono">
                        <span className="px-2 py-1 rounded-lg bg-surface-container-high border border-outline-variant/40">{derived.progressById[derived.continueProblem.id].attempts} রান</span>
                        <span className="px-2 py-1 rounded-lg bg-surface-container-high border border-outline-variant/40">সেরা {derived.progressById[derived.continueProblem.id].best_passed}/{derived.progressById[derived.continueProblem.id].total_tests || '?'} টেস্ট</span>
                        <span className="px-2 py-1 rounded-lg bg-surface-container-high border border-outline-variant/40">{derived.progressById[derived.continueProblem.id].help_requests} AI প্রশ্ন</span>
                      </div>
                    )}
                    <div className="flex items-center justify-between gap-3 pt-1">
                      <div className="flex-1">
                        <div className="flex justify-between text-[10px] font-mono text-on-surface-variant mb-1">
                          <span>সামগ্রিক অগ্রগতি</span><span className="text-on-surface font-bold">{overallPct}%</span>
                        </div>
                        <ProgressBar value={overallPct} />
                      </div>
                      <Button as={Link} to={`/workspace?problem=${derived.continueProblem.id}`} size="md" className="shrink-0">
                        শুরু করুন <ArrowRight className="w-3.5 h-3.5" />
                      </Button>
                    </div>
                  </div>
                ) : (
                  <EmptyState icon={<Crown className="w-5 h-5 text-xp" />} title="সব টাস্ক সম্পন্ন!" action={<Button as={Link} to="/assessment" size="sm">পরীক্ষা দিন <ArrowRight className="w-3.5 h-3.5" /></Button>}>
                    {NCTB_PROBLEMS.length}টি অনুশীলন টাস্কই সমাধান করেছেন। এবার মূল্যায়ন পরীক্ষায় নিজেকে যাচাই করুন।
                  </EmptyState>
                )}
              </SectionCard>

              {/* Activity chart */}
              <SectionCard icon={<Activity className="w-4 h-4 text-primary" />} title="গত ১৪ দিনের কার্যক্রম" subtitle="Activity - last 14 days" className="animate-fade-up stagger-2">
                {chartHasData ? (
                  <div className="h-56">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={data.daily} barGap={2} barCategoryGap="30%" margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
                        <CartesianGrid vertical={false} stroke={isDark ? 'rgba(255,255,255,.07)' : 'rgba(42,38,32,.1)'} />
                        <XAxis dataKey="label" tick={{ fontSize: 10, fill: isDark ? '#9aa9c9' : '#5a5446' }} axisLine={false} tickLine={false} interval={1} />
                        <YAxis allowDecimals={false} tick={{ fontSize: 10, fill: isDark ? '#9aa9c9' : '#5a5446' }} axisLine={false} tickLine={false} />
                        <Tooltip content={<ChartTooltip />} cursor={{ fill: isDark ? 'rgba(255,255,255,0.04)' : 'rgba(42,38,32,0.06)' }} />
                        <Legend iconType="square" iconSize={8} wrapperStyle={{ fontSize: 11 }} />
                        <Bar dataKey="code_runs" name="কোড রান" fill={colors.runs} radius={[4, 4, 0, 0]} maxBarSize={14} />
                        <Bar dataKey="help_requests" name="AI প্রশ্ন" fill={colors.help} radius={[4, 4, 0, 0]} maxBarSize={14} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                ) : (
                  <EmptyState icon={<Activity className="w-5 h-5" />} title="এখনো কোনো কার্যক্রম নেই">
                    Workspace-এ গিয়ে কোড রান করুন — আপনার প্রতিদিনের অগ্রগতি এখানে গ্রাফে দেখা যাবে।
                  </EmptyState>
                )}
              </SectionCard>

              {/* Achievements */}
              <SectionCard
                icon={<Award className="w-4 h-4 text-xp" />} title="অর্জন ও ব্যাজ" subtitle={`${derived.earned.length} of ${derived.badges.length} unlocked`}
                className="animate-fade-up stagger-3"
                action={<span className="text-[11px] font-mono font-bold text-xp">{Math.round((derived.earned.length / derived.badges.length) * 100)}%</span>}
              >
                <div className="grid grid-cols-3 sm:grid-cols-4 lg:grid-cols-6 gap-2.5">
                  {derived.badges.map((b, i) => {
                    const Icon = BADGE_ICONS[b.icon] || Trophy;
                    return (
                      <div
                        key={b.id}
                        title={`${b.title} — ${b.desc}`}
                        className={`group relative aspect-square rounded-2xl border flex flex-col items-center justify-center gap-1 p-2 text-center transition-all ${
                          b.earned
                            ? 'bg-xp/10 border-xp/35 text-xp hover:scale-[1.06] animate-pop'
                            : 'bg-surface-container-high border-outline-variant/40 text-on-surface-variant/45'
                        }`}
                        style={b.earned ? { animationDelay: `${i * 45}ms` } : undefined}
                      >
                        {b.earned ? <Icon className="w-5 h-5" /> : <Lock className="w-4 h-4" />}
                        <span className="text-[9px] font-bold leading-tight line-clamp-2">{bn ? b.bn : b.title}</span>
                      </div>
                    );
                  })}
                </div>
              </SectionCard>
            </div>

            <div className="lg:col-span-5 space-y-4">
              {/* Skill mastery */}
              <SectionCard icon={<TrendingUp className="w-4 h-4 text-primary" />} title="দক্ষতার অগ্রগতি" subtitle="Skill mastery" className="animate-fade-up stagger-2">
                <div className="space-y-3">
                  {derived.mastery.map((m) => (
                    <div key={m.skill}>
                      <div className="flex justify-between text-[11px] mb-1">
                        <span className="font-bold">{m.skill}</span>
                        <span className="font-mono text-on-surface-variant">{m.solved}/{m.total} · <span className={`font-bold ${m.pct >= 100 ? 'text-success' : m.pct > 0 ? 'text-on-surface' : 'text-on-surface-variant'}`}>{m.pct}%</span></span>
                      </div>
                      <ProgressBar value={m.pct} tone={m.pct >= 100 ? 'success' : 'primary'} height="h-1.5" />
                    </div>
                  ))}
                </div>
              </SectionCard>

              {/* Recommended */}
              <SectionCard
                icon={<Sparkles className="w-4 h-4 text-primary" />} title="পরবর্তী অনুশীলন" subtitle="Recommended for you"
                className="animate-fade-up stagger-3"
                action={<Link to="/workspace" className="text-[11px] font-mono font-bold text-primary hover:underline">সব টাস্ক</Link>}
              >
                {derived.recommended.length === 0 ? (
                  <EmptyState icon={<Crown className="w-5 h-5 text-xp" />} title="সব শেষ!">প্রতিটি টাস্ক সমাধান হয়ে গেছে।</EmptyState>
                ) : (
                  <div className="space-y-2">
                    {derived.recommended.map((p) => (
                      <Link key={p.id} to={`/workspace?problem=${p.id}`} className="flex items-center gap-3 bg-surface-container-high rounded-xl border border-outline-variant/40 p-3 card-interactive">
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-1.5 mb-1">
                            <Badge tone="primary">{p.skill}</Badge>
                            <span className="text-[10px] font-mono text-on-surface-variant flex items-center gap-1"><Clock className="w-2.5 h-2.5" />{p.estimated_min}m</span>
                          </div>
                          <div className="text-xs font-bold truncate">{p.title}</div>
                        </div>
                        <ArrowRight className="w-4 h-4 text-primary shrink-0" />
                      </Link>
                    ))}
                  </div>
                )}
              </SectionCard>

              {/* Assessments */}
              <SectionCard
                icon={<FileCheck className="w-4 h-4 text-primary" />} title="পরীক্ষার ফলাফল" subtitle="Assessment results"
                className="animate-fade-up stagger-4"
                action={<Link to="/assessment" className="text-[11px] font-mono font-bold text-primary hover:underline">পরীক্ষা দিন</Link>}
              >
                <div className="space-y-2">
                  {Object.entries(EXAM_LABELS).map(([key, label]) => {
                    const a = data.assessments?.[key];
                    return (
                      <div key={key} className="flex items-center justify-between gap-3 bg-surface-container-high rounded-xl border border-outline-variant/40 px-3 py-2">
                        <div className="min-w-0">
                          <div className="text-xs font-bold truncate">{bn ? label.bn : label.en}</div>
                          <div className="text-[10px] font-mono text-on-surface-variant">{a ? `${a.attempts} বার · ${timeAgo(a.last_at)}` : 'দেওয়া হয়নি'}</div>
                        </div>
                        <div className="text-right shrink-0">
                          <div className={`text-lg font-extrabold font-display ${a ? (a.latest_score >= 60 ? 'text-success' : 'text-warning') : 'text-on-surface-variant/50'}`}>{a ? `${a.latest_score}%` : '—'}</div>
                          {a && a.best_score !== a.latest_score && <div className="text-[9px] font-mono text-on-surface-variant">সেরা {a.best_score}%</div>}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </SectionCard>

              {/* Tutor status */}
              <SectionCard icon={<Bot className="w-4 h-4 text-secondary" />} title="AI টিউটর" subtitle="Tutor status" className="animate-fade-up stagger-5">
                <div className="grid grid-cols-2 gap-2 text-[11px]">
                  {[
                    ['মোড', armLabel(arm)],
                    ['মডেল', rag?.engine?.llm_model || '—'],
                    ['ইনডেক্সড অনুচ্ছেদ', rag ? rag.engine.vector_count.toLocaleString() : '—'],
                    ['কপি করা কোড', `${stats.copy_paste || 0} বার`],
                  ].map(([k, v]) => (
                    <div key={k} className="bg-surface-container-high rounded-xl border border-outline-variant/40 p-2.5">
                      <div className="font-mono text-on-surface-variant uppercase text-[9px] truncate">{k}</div>
                      <div className="font-bold truncate">{v}</div>
                    </div>
                  ))}
                </div>
              </SectionCard>
            </div>
          </div>
        </>
      )}

      {/* ── Recent activity ────────────────────────────────────────────── */}
      {data && (
        <SectionCard icon={<Clock className="w-4 h-4 text-primary" />} title="সাম্প্রতিক কার্যক্রম" subtitle="Recent activity" className="animate-fade-up stagger-4">
          {!(data.recent || []).length ? (
            <EmptyState icon={<Activity className="w-5 h-5" />} title="এখনো কিছু নেই">
              Workspace-এ কোড রান করুন বা AI টিউটরকে প্রশ্ন করুন — প্রতিটি কাজ এখানে লগ হবে।
            </EmptyState>
          ) : (
            <ol className="border-l border-outline-variant/40 ml-3 space-y-3">
              {data.recent.map((ev, i) => {
                const prob = ev.problem_id ? PROBLEM_BY_ID[ev.problem_id] : null;
                const icon = (EVENT_ICON[ev.event_type] || (() => <Activity className="w-3.5 h-3.5 text-on-surface-variant" />))(ev.status);
                return (
                  // Each row is its own positioning context on purpose. The icon used to be
                  // absolutely positioned against the <ol>, but the row's fade-up animation
                  // applies a transform, which makes the <li> the containing block instead -
                  // so the icon landed 11px into the text and hid the first character of
                  // every entry ("rm Switch", "ogin"). Anchoring to the row is deterministic:
                  // the 24px icon sits centred on the timeline line, the text starts 12px past it.
                  <li key={i} className="relative pl-6 animate-fade-up" style={{ animationDelay: `${Math.min(i * 40, 320)}ms` }}>
                    <span className="absolute -left-3 top-0.5 w-6 h-6 rounded-full bg-surface-container-high border border-outline-variant/50 flex items-center justify-center">{icon}</span>
                    <div className="text-xs text-on-surface font-medium">{ev.detail}</div>
                    <div className="text-[10px] font-mono text-on-surface-variant">
                      {timeAgo(ev.timestamp)}{prob ? ` · ${prob.title}` : ev.problem_id ? ` · ${ev.problem_id}` : ''}
                    </div>
                  </li>
                );
              })}
            </ol>
          )}
        </SectionCard>
      )}
    </div>
  );
};
