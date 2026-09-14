// Progression derived from the dashboard telemetry - XP, levels and badges give
// students a visible reason to come back between assessments.
import { NCTB_PROBLEMS } from './problems';

export const XP_RULES = [
  { key: 'problems_solved', xp: 100, label: 'Task solved' },
  { key: 'problems_attempted', xp: 15, label: 'Task attempted' },
  { key: 'code_runs', xp: 5, label: 'Code run' },
  { key: 'help_requests', xp: 3, label: 'Question asked' },
  { key: 'active_days', xp: 20, label: 'Active day' },
];

export const LEVELS = [
  { level: 1, min: 0, title: 'Novice Coder', bn: 'নবীন কোডার' },
  { level: 2, min: 120, title: 'Loop Learner', bn: 'লুপ শিক্ষার্থী' },
  { level: 3, min: 320, title: 'Logic Builder', bn: 'লজিক বিল্ডার' },
  { level: 4, min: 620, title: 'Syntax Slayer', bn: 'সিনট্যাক্স মাস্টার' },
  { level: 5, min: 1000, title: 'Algorithm Adept', bn: 'অ্যালগরিদম দক্ষ' },
  { level: 6, min: 1500, title: 'Debug Champion', bn: 'ডিবাগ চ্যাম্পিয়ন' },
  { level: 7, min: 2200, title: 'ICT Grandmaster', bn: 'আইসিটি গ্র্যান্ডমাস্টার' },
];

export function computeXp(stats = {}, assessments = {}) {
  let xp = XP_RULES.reduce((sum, rule) => sum + (Number(stats[rule.key]) || 0) * rule.xp, 0);
  xp += Object.values(assessments).reduce((sum, a) => sum + Math.round((a.best_score || 0) * 1.5), 0);
  return xp;
}

export function levelInfo(xp) {
  const index = Math.max(0, LEVELS.findIndex((l, i) => xp >= l.min && (i === LEVELS.length - 1 || xp < LEVELS[i + 1].min)));
  const current = LEVELS[index];
  const next = LEVELS[index + 1] || null;
  const span = next ? next.min - current.min : 1;
  const into = xp - current.min;
  return {
    ...current,
    xp,
    next,
    xpIntoLevel: into,
    xpForNext: next ? next.min - xp : 0,
    progressPct: next ? Math.min(100, Math.round((into / span) * 100)) : 100,
  };
}

// Each badge reads the same dashboard payload, so unlocks need no extra storage.
export const BADGES = [
  { id: 'first_run', icon: 'Play', title: 'Hello, World', bn: 'প্রথম রান', desc: 'Run your first program', test: (s) => (s.stats.code_runs || 0) >= 1 },
  { id: 'first_solve', icon: 'CheckCircle2', title: 'First Solve', bn: 'প্রথম সমাধান', desc: 'Pass every test on a task', test: (s) => (s.stats.problems_solved || 0) >= 1 },
  { id: 'curious', icon: 'Bot', title: 'Curious Mind', bn: 'কৌতূহলী', desc: 'Ask the AI tutor 5 questions', test: (s) => (s.stats.help_requests || 0) >= 5 },
  { id: 'streak_3', icon: 'Flame', title: 'On Fire', bn: 'ধারাবাহিক', desc: 'Practise 3 days in a row', test: (s) => (s.stats.streak_days || 0) >= 3 },
  { id: 'streak_7', icon: 'Zap', title: 'Week Warrior', bn: 'সপ্তাহ যোদ্ধা', desc: 'Keep a 7-day streak', test: (s) => (s.stats.streak_days || 0) >= 7 },
  { id: 'loops', icon: 'Repeat', title: 'Loop Master', bn: 'লুপ মাস্টার', desc: 'Solve every loop task', test: (s) => solvedSkill(s, 'Loops & Accumulation') },
  { id: 'html', icon: 'Code2', title: 'Web Designer', bn: 'ওয়েব ডিজাইনার', desc: 'Solve all Chapter 4 HTML tasks', test: (s) => ['HTML Tables', 'HTML Links & Images', 'HTML Lists'].every((k) => solvedSkill(s, k)) },
  { id: 'assessment', icon: 'FileCheck', title: 'Test Taker', bn: 'পরীক্ষার্থী', desc: 'Complete an assessment', test: (s) => Object.keys(s.assessments || {}).length >= 1 },
  { id: 'high_score', icon: 'Trophy', title: 'High Scorer', bn: 'উচ্চ স্কোর', desc: 'Score 80% or more on a test', test: (s) => Object.values(s.assessments || {}).some((a) => (a.best_score || 0) >= 80) },
  { id: 'halfway', icon: 'Target', title: 'Halfway Hero', bn: 'অর্ধেক পথ', desc: `Solve ${Math.ceil(NCTB_PROBLEMS.length / 2)} tasks`, test: (s) => (s.stats.problems_solved || 0) >= Math.ceil(NCTB_PROBLEMS.length / 2) },
  { id: 'completionist', icon: 'Crown', title: 'Completionist', bn: 'সম্পূর্ণকারী', desc: 'Solve every practice task', test: (s) => (s.stats.problems_solved || 0) >= NCTB_PROBLEMS.length },
  { id: 'independent', icon: 'Sparkles', title: 'Independent', bn: 'স্বনির্ভর', desc: 'Solve 3 tasks without asking the AI', test: (s) => (s.problems || []).filter((p) => p.solved && !p.help_requests).length >= 3 },
];

function solvedSkill(snapshot, skill) {
  const ids = NCTB_PROBLEMS.filter((p) => p.skill === skill).map((p) => p.id);
  if (!ids.length) return false;
  const solved = new Set((snapshot.problems || []).filter((p) => p.solved).map((p) => p.problem_id));
  return ids.every((id) => solved.has(id));
}

export function evaluateBadges(snapshot) {
  const safe = { stats: {}, assessments: {}, problems: [], ...(snapshot || {}) };
  return BADGES.map((b) => {
    let earned = false;
    try {
      earned = !!b.test(safe);
    } catch (_) {
      earned = false;
    }
    return { ...b, earned };
  });
}

export const DAILY_GOAL_RUNS = 3;
