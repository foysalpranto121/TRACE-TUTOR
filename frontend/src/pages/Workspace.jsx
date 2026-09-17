import { useState, useEffect, useRef } from 'react';
import { useAuth } from '../context/useAuth';
import { CodeEditor } from '../components/Editor/CodeEditor';
import { ReasoningTracePanel } from '../components/TutorPanel/ReasoningTracePanel';
import { AnswerOnlyPanel } from '../components/TutorPanel/AnswerOnlyPanel';
import { apiService } from '../services/api';
import { useResetOnChange } from '../hooks/useResetOnChange';
import { NCTB_PROBLEMS } from '../data/problems';
import { useSearchParams } from 'react-router-dom';
import { useCelebrate } from '../components/ui/useCelebrate';
import { computeXp, levelInfo, evaluateBadges, BADGES } from '../data/gamification';
import { BookOpen, CheckCircle2, PanelLeftClose, PanelLeft } from 'lucide-react';

const snapshotProgress = (d) => {
  const xp = computeXp(d.stats || {}, d.assessments || {});
  return {
    xp,
    level: levelInfo(xp).level,
    badges: new Set(evaluateBadges(d).filter((b) => b.earned).map((b) => b.id)),
    solved: new Set((d.problems || []).filter((p) => p.solved).map((p) => p.problem_id)),
  };
};

export const Workspace = () => {
  const { user, arm, language } = useAuth();
  const celebrate = useCelebrate();
  const progressRef = useRef(null);
  const [showProblemPane, setShowProblemPane] = useState(true);

  const nctbProblems = NCTB_PROBLEMS;

  const [searchParams] = useSearchParams();
  const requestedProblem = nctbProblems.find((p) => p.id === searchParams.get('problem'));
  const [activeProblem, setActiveProblem] = useState(requestedProblem || nctbProblems[0]);
  const [currentCode, setCurrentCode] = useState((requestedProblem || nctbProblems[0]).starterCode);
  const [lastCompile, setLastCompile] = useState(null);
  const [compilerInfo, setCompilerInfo] = useState(null);

  const [tutorState, setTutorState] = useState({
    isLoading: false,
    traceData: null,
    groundedPassage: null,
    error: null,
  });

  // Switching problems swaps the editor contents during render, not after paint.
  useResetOnChange(activeProblem?.id, () => {
    setCurrentCode(activeProblem.starterCode);
    setLastCompile(null);
  });

  useEffect(() => {
    apiService.getCodeStatus().then(setCompilerInfo).catch(() => setCompilerInfo({ ready: false }));
  }, []);

  // Progress snapshot so a successful run can show exactly what the student just earned.
  useEffect(() => {
    apiService.getDashboard().then((d) => { progressRef.current = snapshotProgress(d); }).catch(() => {});
  }, []);

  const handleCompileResult = async (out) => {
    setLastCompile(out);
    const before = progressRef.current;
    if (out.status !== 'SUCCESS' || !before || before.solved.has(activeProblem.id)) return;

    // The run is logged fire-and-forget by the editor; give it a moment to land.
    await new Promise((r) => setTimeout(r, 700));
    try {
      const after = snapshotProgress(await apiService.getDashboard());
      const gained = after.xp - before.xp;
      if (gained > 0) {
        celebrate.toast({ kind: 'xp', title: 'টাস্ক সমাধান হয়েছে!', subtitle: activeProblem.title, amount: `${gained} XP` });
      }
      [...after.badges].filter((id) => !before.badges.has(id)).forEach((id, i) => {
        const badge = BADGES.find((b) => b.id === id);
        if (badge) setTimeout(() => celebrate.toast({ kind: 'badge', title: `নতুন ব্যাজ: ${badge.title}`, subtitle: badge.desc }), 600 + i * 400);
      });
      if (after.level > before.level) setTimeout(() => celebrate.levelUp(levelInfo(after.xp)), 900);
      progressRef.current = after;
    } catch (_) { /* celebration is best-effort */ }
  };

  // Log workspace session start
  useEffect(() => {
    apiService.logTelemetry('WORKSPACE_ENTER', {
      user_id: user?.id,
      arm: arm,
      problem_id: activeProblem.id,
      timestamp: new Date().toISOString(),
    });
  }, [arm, user, activeProblem.id]);

  // `extra` carries anything the panel knows that the server should record with the
  // turn - today the view (dual / rag / independent) the question was asked from.
  const handleRequestHelp = async (queryText, extra = {}) => {
    setTutorState({ isLoading: true, traceData: null, groundedPassage: null, error: null });

    // HELP_REQUEST is logged server-side in query_tutor now (with arm, paper, ai_status
    // and whether it was refused), so the assessment chat and the workspace are both
    // recorded and cannot disagree. No client-side HELP_REQUEST here.
    const compilerOutput = lastCompile?.status === 'COMPILE_ERROR'
      ? lastCompile.compile_output
      : lastCompile?.testResults?.filter((t) => !t.passed).map((t) => `Test ${t.id} input=${t.input} expected="${t.expected}" actual="${t.actual}" ${t.stderr || ''}`).join('\n') || '';

    try {
      const res = await apiService.queryTutor(queryText, currentCode, activeProblem.id, arm, {
        language,
        problem_title: activeProblem.title,
        problem_description: activeProblem.description_en,
        compiler_output: compilerOutput,
        ...extra,
      });
      setTutorState({ isLoading: false, traceData: res, groundedPassage: res.grounded_passage, error: null });
    } catch (err) {
      // A refusal because a no-AI paper is open is a rule, not a failure; the panels
      // present it calmly so a student mid-pre-test does not think the system is broken.
      const errorKind = err.body?.reason === 'paper_in_progress' ? 'policy' : 'failure';
      setTutorState({ isLoading: false, traceData: null, groundedPassage: null, error: err.message, errorKind });
    }
  };

  const compilerBadge = activeProblem.lang === 'html'
    ? 'HTML5 Preview Ready'
    : !compilerInfo
      ? 'Checking compiler...'
      : compilerInfo.ready
        ? `${compilerInfo.c} Ready`
        : 'Compiler Offline';
  const compilerOk = activeProblem.lang === 'html' || compilerInfo?.ready;

  return (
    <div className="flex-1 min-h-0 flex flex-col space-y-3 overflow-hidden">
      {/* Top Professional Action & Task Bar */}
      <div className="bg-surface-container px-3 py-2 rounded-2xl border border-outline-variant/30 flex items-center justify-between gap-2 shrink-0 shadow-md">
        <div className="flex items-center gap-2 min-w-0">
          {/* Toggle Problem Sidebar Button - the panel stacks on mobile, so only offer it on desktop */}
          <button
            onClick={() => setShowProblemPane(!showProblemPane)}
            className="hidden lg:flex px-3 py-1.5 rounded-xl bg-surface-container-high hover:bg-surface-container-highest text-on-surface text-xs font-bold items-center gap-2 border border-outline-variant/30 transition-all press shrink-0"
            title={showProblemPane ? 'Collapse problem panel for maximum code editor space' : 'Expand problem panel sidebar'}
          >
            {showProblemPane ? <PanelLeftClose className="w-4 h-4 text-primary" /> : <PanelLeft className="w-4 h-4 text-primary" />}
            <span className="hidden xl:inline">{showProblemPane ? 'Hide Task Panel' : 'Show Task Panel'}</span>
          </button>

          <div className="h-4 w-px bg-outline-variant/30 hidden lg:block" />

          {/* NCTB Task Selector Dropdown */}
          <div className="flex items-center gap-2 min-w-0">
            <BookOpen className="w-4 h-4 text-primary hidden md:inline shrink-0" />
            <span className="text-xs text-on-surface-variant font-bold hidden xl:inline shrink-0">NCTB Task:</span>
            <select
              value={activeProblem.id}
              onChange={(e) => {
                const selected = nctbProblems.find((p) => p.id === e.target.value);
                if (selected) setActiveProblem(selected);
              }}
              className="bg-surface-container-high text-on-surface rounded-xl px-3 py-1.5 text-xs font-bold border border-outline-variant/40 focus:border-primary outline-none cursor-pointer w-full min-w-0 truncate"
            >
              {nctbProblems.map((prob) => (
                <option key={prob.id} value={prob.id} className="bg-surface-container text-on-surface">
                  {prob.title}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Right Status Badge */}
        <div className="flex items-center gap-2 shrink-0">
          <span className={`px-2.5 py-1 rounded-lg text-xs font-mono font-bold border flex items-center gap-1.5 shadow-sm ${
            compilerOk ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/30' : 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/30'
          }`}>
            <span className={`w-2 h-2 rounded-full ${compilerOk ? 'bg-emerald-500 animate-pulse' : 'bg-amber-500'}`} />
            <span className="hidden sm:inline">{compilerBadge}</span>
            <span className="sm:hidden">{activeProblem.lang === 'html' ? 'HTML5' : 'C'}</span>
          </span>
        </div>
      </div>

      {/* Main workspace: panels stack and scroll on mobile, fill the viewport side-by-side on desktop */}
      <div className="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-12 gap-3 lg:gap-4 overflow-y-auto lg:overflow-hidden pb-1">
        {/* Column 1: Problem Description (3 cols when expanded) */}
        {showProblemPane && (
          <div className="lg:col-span-3 bg-surface-container rounded-2xl border border-outline-variant/30 flex flex-col overflow-hidden shadow-xl transition-all duration-300 max-h-[320px] lg:max-h-none">
            {/* Header */}
            <div className="p-3.5 bg-surface-container-high border-b border-outline-variant/30 flex items-center justify-between">
              <div className="flex items-center gap-2 text-xs font-bold text-on-surface">
                <BookOpen className="w-4 h-4 text-primary" />
                <span>Problem Task Details</span>
              </div>
              <span className="px-2 py-0.5 rounded bg-primary/10 text-primary text-[10px] font-mono font-bold border border-primary/30">
                {activeProblem.difficulty}
              </span>
            </div>

            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              <div>
                <span className="text-[10px] font-mono text-primary font-bold uppercase tracking-wider block mb-1">
                  {activeProblem.chapter}
                </span>
                <h2 className="text-sm font-extrabold text-on-surface leading-snug">
                  {activeProblem.title}
                </h2>
              </div>

              <div className="text-xs text-on-surface-variant leading-relaxed bg-surface-container-lowest p-3.5 rounded-xl border border-outline-variant/20 font-medium">
                {language === 'bn' ? activeProblem.description_bn : activeProblem.description_en}
              </div>

              {/* Input / Output Format */}
              <div className="space-y-3 pt-1">
                <div>
                  <span className="text-[11px] font-mono font-bold text-primary uppercase tracking-wider block">Input Format</span>
                  <p className="text-xs text-on-surface-variant font-mono">{activeProblem.input_format}</p>
                </div>
                <div>
                  <span className="text-[11px] font-mono font-bold text-primary uppercase tracking-wider block">Output Format</span>
                  <p className="text-xs text-on-surface-variant font-mono">{activeProblem.output_format}</p>
                </div>
              </div>

              {/* Requirements checklist (HTML) or sample test cases (C) */}
              <div className="space-y-2 pt-1">
                <span className="text-[11px] font-mono font-bold text-on-surface uppercase tracking-wider block">
                  {activeProblem.html_checks?.length ? 'Requirements (auto-checked)' : 'Sample Test Cases'}
                </span>
                {activeProblem.html_checks?.map((chk, idx) => (
                  <div key={idx} className="bg-surface-container-high p-2.5 rounded-xl border border-outline-variant/30 text-xs flex items-start gap-2">
                    <CheckCircle2 className="w-3.5 h-3.5 text-primary shrink-0 mt-0.5" />
                    <span className="text-on-surface font-medium">{chk.name}</span>
                  </div>
                ))}
                {!activeProblem.html_checks?.length && activeProblem.sample_cases.map((sc, idx) => (
                  <div key={idx} className="bg-surface-container-high p-3 rounded-xl border border-outline-variant/30 text-xs font-mono space-y-1">
                    <div className="flex justify-between text-on-surface-variant">
                      <span>Input:</span> <span className="text-primary font-bold">{sc.input}</span>
                    </div>
                    <div className="flex justify-between text-on-surface-variant">
                      <span>Output:</span> <span className="text-emerald-400 font-bold">{sc.output}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Column 2: Code Editor Studio (7-8 cols if problem sidebar collapsed, 5 cols if open) */}
        <div className={`${showProblemPane ? 'lg:col-span-5' : 'lg:col-span-7 xl:col-span-8'} flex flex-col lg:h-full transition-all duration-300 min-h-[560px] lg:min-h-0`}>
          <CodeEditor
            key={activeProblem.id}
            initialCode={activeProblem.starterCode}
            sampleCases={activeProblem.sample_cases}
            htmlChecks={activeProblem.html_checks || []}
            language={activeProblem.lang || 'c'}
            activeProblem={activeProblem}
            onCodeChange={setCurrentCode}
            onCompileResult={handleCompileResult}
          />
        </div>

        {/* Column 3: Dynamic AI Tutor Sidebar (4-5 cols beside the C Editor) */}
        <div className={`${showProblemPane ? 'lg:col-span-4' : 'lg:col-span-5 xl:col-span-4'} flex flex-col lg:h-full transition-all duration-300 min-h-[440px] lg:min-h-0`}>
          {arm === 'REASONING_VISIBLE' ? (
            <ReasoningTracePanel
              traceData={tutorState.traceData}
              groundedPassage={tutorState.groundedPassage}
              isLoading={tutorState.isLoading}
              error={tutorState.error}
              errorKind={tutorState.errorKind}
              onRequestHelp={handleRequestHelp}
            />
          ) : (
            <AnswerOnlyPanel
              solutionData={tutorState.traceData}
              isLoading={tutorState.isLoading}
              error={tutorState.error}
              errorKind={tutorState.errorKind}
              onRequestHelp={handleRequestHelp}
            />
          )}
        </div>
      </div>
    </div>
  );
};

