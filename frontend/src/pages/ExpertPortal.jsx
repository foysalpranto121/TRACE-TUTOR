import { useState, useEffect } from 'react';
import { expertText, contentLanguage } from '../services/expertText';
import { useAuth } from '../context/useAuth';
import { formatScore } from '../services/score';
import { formatTimingDate, formatElapsedDays } from '../services/assessmentTiming';
import { apiService } from '../services/api';
import { useResetOnChange } from '../hooks/useResetOnChange';
import {
  Brain, BookOpen, CheckCircle2, Sliders, AlertTriangle, BarChart2, UserCheck, Award, FileCode,
  CheckSquare, ClipboardList, Users, RefreshCw, ChevronLeft, ChevronRight,
} from 'lucide-react';
import { Card, SectionCard, Badge, Button, StatTile, EmptyState, Skeleton } from '../components/ui';

const CRITERIA = [
  { key: 'alignment', bn: '১. কারিকুলাম সংগতি', en: 'Curriculum alignment' },
  { key: 'accuracy', bn: '২. কারিগরি নির্ভুলতা', en: 'Technical accuracy' },
  { key: 'clarity', bn: '৩. ভাষার স্পষ্টতা', en: 'Language clarity' },
  { key: 'difficulty', bn: '৪. একাদশ-দ্বাদশ মানের কাঠিন্য', en: 'Grade 11-12 difficulty' },
  { key: 'answerability', bn: '৫. উত্তরযোগ্যতা', en: 'Defensible answerability' },
];
const BLANK_RATINGS = { alignment: null, accuracy: null, clarity: null, difficulty: null, answerability: null };
const autoTone = (status) => (status === 'SUCCESS' ? 'success' : status ? 'danger' : 'neutral');
const assignedToMe = (row) => row.is_assigned !== false;
const ratedByMe = (row) => Boolean(row.my_rating);
const gradedByMe = (row) => row.my_grade_completed ?? (row.assigned_marks != null);
const scopeRows = (rows, scope, completed) => scope === 'all' ? rows
  : rows.filter(scope === 'history' ? completed : assignedToMe);

const WorkScope = ({ rows, scope, completed, onChange, disabled }) => {
  const { language } = useAuth();
  const t = (key) => expertText(language, key);
  const assigned = rows.filter(assignedToMe);
  const done = assigned.filter(completed).length;
  return (
    <Card className="p-4 flex flex-wrap items-center justify-between gap-3">
      <div>
        <p className="text-xs font-bold text-on-surface">{t('Your assigned work')}: {assigned.length}</p>
        <p className="text-[11px] text-on-surface-variant mt-1">{t('Completed')}: {done} · {t('Remaining')}: {assigned.length - done}</p>
      </div>
      <div className="flex flex-wrap gap-2" role="group" aria-label={t('Work list')}>
        {[
          ['assigned', 'Assigned', assigned.length],
          ['history', 'Earlier work', rows.filter(completed).length],
          ['all', 'More', rows.length],
        ].map(([value, label, count]) => (
          <Button key={value} size="sm" variant={scope === value ? 'primary' : 'surface'}
            aria-pressed={scope === value} disabled={disabled} onClick={() => onChange(value)}>
            {t(label)} ({count})
          </Button>
        ))}
      </div>
    </Card>
  );
};

const formatWhen = (iso) => {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString([], { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
};

const CodeBlock = ({ children }) => (
  <div className="bg-surface-container-lowest p-4 rounded-xl border border-outline-variant/30 overflow-x-auto shadow-inner">
    <pre lang={contentLanguage(children)} className="font-mono text-xs text-primary leading-relaxed whitespace-pre-wrap">{children}</pre>
  </div>
);

const ErrorBanner = ({ children, onRetry }) => {
  const { language } = useAuth();
  const t = (key) => expertText(language, key);
  return (
  <div className="bg-danger/10 border border-danger/30 rounded-xl p-4 text-xs text-danger flex flex-wrap items-center gap-3">
    <AlertTriangle className="w-4 h-4 shrink-0" />
    <span className="flex-1 min-w-0">{children}</span>
    {onRetry && <Button variant="surface" size="sm" onClick={onRetry}><RefreshCw className="w-3.5 h-3.5" /> {t("Retry")}</Button>}
  </div>
  );
};

// 1-4 buttons rather than a slider: a slider always carries a value, so an untouched
// rubric would silently submit a default score the expert never chose.
const RatingScale = ({ bn, en, value, onChange, disabled }) => {
  const { language } = useAuth();
  const t = (key) => expertText(language, key);
  return (
  <div className="space-y-1.5">
    <div className="flex items-baseline justify-between gap-2">
      <span className="text-xs font-bold text-on-surface">
        {language === 'en' ? en : <><span lang="bn">{bn}</span> <span lang="en" className="font-medium text-on-surface-variant">({en})</span></>}
      </span>
      <span className="text-[10px] font-mono font-bold text-on-surface-variant shrink-0">{value ? `${value} / 4` : t("Unassigned")}</span>
    </div>
    <div className="grid grid-cols-4 gap-1.5">
      {[1, 2, 3, 4].map((n) => (
        <button
          key={n}
          type="button"
          aria-label={language === 'en' ? `${en}: ${n} of 4` : `${bn}: ${n} / 4`}
          disabled={disabled}
          aria-pressed={value === n}
          onClick={() => onChange(n)}
          className={`py-1.5 rounded-lg border font-mono text-xs font-extrabold press transition-colors ${
            value === n
              ? 'bg-primary text-on-primary border-primary'
              : 'bg-surface-container-high text-on-surface-variant border-outline-variant/40 hover:border-primary/40 hover:text-on-surface'
          }`}
        >
          {n}
        </button>
      ))}
    </div>
  </div>
  );
};

// Research drafts stay in memory and are scoped to the authenticated account.
export const ExpertPortal = () => {
  const { user, role } = useAuth();
  return <ExpertWorkbench key={String(user?.id ?? '') + ':' + role} />;
};

const ExpertWorkbench = () => {
  const { language } = useAuth();
  const t = (key) => expertText(language, key);
  const examLabel = (type) => t(({ pre: 'Pre-test', post: 'Post-test', transfer: 'Transfer', withdrawal: 'Withdrawal' })[type] || type || '—');
  const [activeTab, setActiveTab] = useState('cvi_certification'); // 'cvi_certification' or 'student_marking'

  // Tab 1: CVI certification
  const [reviewData, setReviewData] = useState(null);
  const [queueLoading, setQueueLoading] = useState(true);
  const [queueError, setQueueError] = useState(null);
  const [activeItemIndex, setActiveItemIndex] = useState(0);
  const [itemScope, setItemScope] = useState('assigned');
  const [drafts, setDrafts] = useState({});
  const [gradeDrafts, setGradeDrafts] = useState({});
  const [ratingBusy, setRatingBusy] = useState(false);
  const hasDrafts = Object.keys(drafts).length > 0 || Object.keys(gradeDrafts).length > 0;
  useEffect(() => {
    if (!hasDrafts) return undefined;
    const warnBeforeLeaving = (event) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', warnBeforeLeaving);
    return () => window.removeEventListener('beforeunload', warnBeforeLeaving);
  }, [hasDrafts]);
  const [ratingError, setRatingError] = useState(null);
  const [ratingConflict, setRatingConflict] = useState(false);
  const [ratingSaved, setRatingSaved] = useState(null);

  // Tab 2: student submission marking
  const [submissions, setSubmissions] = useState([]);
  const [subsLoading, setSubsLoading] = useState(true);
  const [subsError, setSubsError] = useState(null);
  const [selectedSubId, setSelectedSubId] = useState(null);
  const [submissionScope, setSubmissionScope] = useState('assigned');
  const [gradeBusy, setGradeBusy] = useState(false);
  const [gradeError, setGradeError] = useState(null);
  const [gradeConflict, setGradeConflict] = useState(false);
  const [gradeSaved, setGradeSaved] = useState(null);

  // Two entry points each. `fetch*` touches state only after an await, so the mount
  // effect can call it; `load*` adds the synchronous spinner flip and is what event
  // handlers (submit a rating, save a grade) call to refresh afterwards.
  const fetchQueue = async () => {
    try {
      const data = await apiService.getExpertQueue();
      setReviewData(data);
      setQueueError(null);
      return data;
    } catch (err) {
      setQueueError(err.message);
      return null;
    } finally {
      setQueueLoading(false);
    }
  };

  const loadQueue = () => {
    setQueueLoading(true);
    return fetchQueue();
  };

  const fetchSubmissions = async (scope = 'assigned') => {
    try {
      const data = await apiService.getStudentSubmissions();
      const rows = data.submissions || [];
      setSubmissions(rows);
      const visible = scopeRows(rows, scope, gradedByMe);
      setSelectedSubId((prev) => (visible.some((s) => s.id === prev) ? prev : visible[0]?.id ?? null));
      setSubsError(null);
      return rows;
    } catch (err) {
      setSubsError(err.message);
    } finally {
      setSubsLoading(false);
    }
  };

  const loadSubmissions = () => {
    setSubsLoading(true);
    return fetchSubmissions(submissionScope);
  };

  useEffect(() => {
    // Wrapped so both fetches write state after an await rather than during the effect.
    (async () => { await Promise.all([fetchQueue(), fetchSubmissions()]); })();
  }, []);

  const allItems = reviewData?.items_to_review || [];
  const items = scopeRows(allItems, itemScope, ratedByMe);
  const visibleSubmissions = scopeRows(submissions, submissionScope, gradedByMe);
  const itemIndex = Math.min(activeItemIndex, Math.max(0, items.length - 1));
  const stats = reviewData?.cvi_stats;
  const activeItem = items[itemIndex];
  const activeSub = visibleSubmissions.find((s) => s.id === selectedSubId) || null;
  const changeItemScope = (scope) => {
    const next = scopeRows(allItems, scope, ratedByMe);
    setActiveItemIndex(Math.max(0, next.findIndex((item) => item.id === activeItem?.id)));
    setItemScope(scope);
    setRatingSaved(null);
  };
  const changeSubmissionScope = (scope) => {
    const next = scopeRows(submissions, scope, gradedByMe);
    setSelectedSubId(next.some((sub) => sub.id === selectedSubId) ? selectedSubId : next[0]?.id ?? null);
    setSubmissionScope(scope);
  };
  const gradeDraft = gradeDrafts[selectedSubId];
  const assignedMarks = gradeDraft?.marks ?? activeSub?.assigned_marks ?? '';
  const teacherFeedback = gradeDraft?.feedback ?? activeSub?.feedback ?? '';
  const gradeRevision = gradeDraft ? gradeDraft.revision : activeSub?.grade_revision ?? null;
  const updateGradeDraft = (patch) => {
    if (!activeSub || gradeBusy || subsLoading) return;
    setGradeDrafts((previous) => ({ ...previous, [activeSub.id]: {
      marks: assignedMarks, feedback: teacherFeedback, revision: gradeRevision,
      ...previous[activeSub.id], ...patch,
    } }));
    setGradeSaved(null);
  };
  const serverScore = t(formatScore(activeSub?.score_pct, activeSub?.grading_status));

  const draft = drafts[activeItem?.id];
  const ratings = draft?.ratings ?? (activeItem?.my_rating
    ? Object.fromEntries(CRITERIA.map(({ key }) => [key, activeItem.my_rating[key] ?? null]))
    : BLANK_RATINGS);
  const cviFeedback = draft?.feedback ?? activeItem?.my_rating?.feedback ?? '';
  const updateDraft = (patch) => {
    if (!activeItem || ratingBusy) return;
    setDrafts((previous) => ({ ...previous, [activeItem.id]: {
      ratings, feedback: cviFeedback, revision: activeItem.rating_revision ?? null,
      ...previous[activeItem.id], ...patch,
    } }));
    setRatingSaved(null);
  };
  useResetOnChange(activeItem?.id, () => { setRatingError(null); setRatingConflict(false); });

  // Values derive from the selected record's draft or server row, never another student.
  useResetOnChange(selectedSubId, () => {
    setGradeConflict(false);
    setGradeError(null);
    setGradeSaved(null);
  });

  const ratingsComplete = CRITERIA.every(({ key }) => Number.isInteger(ratings[key]) && ratings[key] >= 1 && ratings[key] <= 4);

  const handleSubmitCviReview = async () => {
    if (!activeItem || !ratingsComplete) return;
    setRatingBusy(true);
    setRatingError(null);
    setRatingSaved(null);
    try {
      const res = await apiService.submitExpertRating(activeItem.id, ratings, cviFeedback, draft ? draft.revision : activeItem.rating_revision ?? null);
      setDrafts((previous) => {
        const next = { ...previous };
        delete next[activeItem.id];
        return next;
      });
      // Preserve the successful write even if reloading the queue fails.
      setReviewData((previous) => ({ ...previous, items_to_review: previous.items_to_review.map((item) =>
        item.id === activeItem.id ? { ...item, my_rating: { ...ratings, feedback: cviFeedback }, rating_revision: res.rating_revision } : item) }));
      setRatingSaved(res);
      setRatingConflict(false);
      // CVI is recomputed server-side from the stored rows, so re-read it instead of guessing.
      const fresh = await loadQueue();
      const refreshedItems = fresh ? scopeRows(fresh.items_to_review || [], itemScope, ratedByMe) : items;
      const savedIndex = refreshedItems.findIndex((item) => item.id === activeItem.id);
      setActiveItemIndex(Math.min(Math.max(0, savedIndex + 1), Math.max(0, refreshedItems.length - 1)));
    } catch (err) {
      setRatingError(err.message);
      setRatingConflict(err.status === 409);
    } finally {
      setRatingBusy(false);
    }
  };

  const handleGradeSubmission = async () => {
    if (!activeSub) return;
    const marks = Number(assignedMarks);
    if (String(assignedMarks).trim() === '' || !Number.isInteger(marks) || marks < 0 || marks > 100) {
      setGradeError('Please enter a mark from 0 to 100.');
      return;
    }
    setGradeBusy(true);
    setGradeError(null);
    setGradeSaved(null);
    try {
      const res = await apiService.gradeSubmission(activeSub.id, marks, teacherFeedback, gradeRevision);
      setGradeSaved(res);
      setGradeConflict(false);
      setGradeDrafts((previous) => { const next = { ...previous }; delete next[activeSub.id]; return next; });
      setSubmissions((previous) => previous.map((sub) => sub.id === activeSub.id
        ? { ...sub, assigned_marks: res.assigned_marks, feedback: teacherFeedback, grade_revision: res.grade_revision,
          my_grade_completed: true, status: 'GRADED' } : sub));
      await loadSubmissions(); // status and graded_by come back from the server, never assumed here
    } catch (err) {
      setGradeError(err.message);
      setGradeConflict(err.status === 409);
    } finally {
      setGradeBusy(false);
    }
  };

  const reloadRating = async () => {
    const fresh = await loadQueue();
    if (!fresh) return;
    setDrafts((previous) => { const next = { ...previous }; delete next[activeItem.id]; return next; });
    setRatingError(null); setRatingConflict(false);
  };
  const reloadGrade = async () => {
    const rows = await loadSubmissions();
    const fresh = rows?.find((sub) => sub.id === selectedSubId);
    if (!fresh) return;
    setGradeDrafts((previous) => { const next = { ...previous }; delete next[selectedSubId]; return next; });
    setGradeError(null); setGradeConflict(false); setGradeSaved(null);
  };

  return (
    <div lang={language === 'en' ? 'en' : 'bn'} className="max-w-7xl mx-auto w-full space-y-5 pb-10">
      {/* Header & tab selector */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-outline-variant/20 pb-4">
        <div>
          <h1 className="text-2xl font-extrabold font-display text-on-surface flex items-center gap-2">
            <Brain className="w-7 h-7 text-primary" /> {t("Expert workbench")}
          </h1>
          <p className="text-xs text-on-surface-variant font-medium">
            {t("Item certification & student code marking")}
          </p>
        </div>

        <div className="flex items-center gap-1 bg-surface-container p-1 rounded-xl border border-outline-variant/30 text-xs font-semibold shadow-sm">
          <button
            onClick={() => setActiveTab('cvi_certification')}
            className={`px-4 py-2 rounded-lg transition-all flex items-center gap-2 ${
              activeTab === 'cvi_certification' ? 'bg-primary text-on-primary font-bold shadow-sm' : 'text-on-surface-variant hover:text-on-surface'
            }`}
          >
            <Sliders className="w-4 h-4" /> {t("CVI certification")} ({allItems.filter(assignedToMe).length})
          </button>
          <button
            onClick={() => setActiveTab('student_marking')}
            className={`px-4 py-2 rounded-lg transition-all flex items-center gap-2 ${
              activeTab === 'student_marking' ? 'bg-primary text-on-primary font-bold shadow-sm' : 'text-on-surface-variant hover:text-on-surface'
            }`}
          >
            <UserCheck className="w-4 h-4" /> {t("Code grading")} ({submissions.filter(assignedToMe).length})
          </button>
        </div>
      </div>

      {/* TAB 1: QUESTION BANK CVI CERTIFICATION */}
      {activeTab === 'cvi_certification' && (
        <div className="space-y-5">
          {queueError && <ErrorBanner onRetry={loadQueue}>{t("Could not load the review queue:")} {queueError}</ErrorBanner>}

          {queueLoading && !reviewData ? (
            <div className="space-y-4">
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-24" />)}</div>
              <div className="grid lg:grid-cols-12 gap-5"><Skeleton className="h-96 lg:col-span-7" /><Skeleton className="h-96 lg:col-span-5" /></div>
            </div>
          ) : reviewData && (
            <>
              <WorkScope rows={allItems} scope={itemScope} completed={ratedByMe}
                onChange={changeItemScope} disabled={queueLoading || ratingBusy} />
              {stats && (
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                  <StatTile icon={<ClipboardList className="w-5 h-5" />} label={t("Items in bank")} value={stats.total_items} hint={t("Total items in the bank")} color="sky" />
                  <StatTile icon={<CheckSquare className="w-5 h-5" />} label={t("Rated items")} value={stats.rated_items} hint={t("Items with ratings")} color="emerald" delay={60} />
                  <StatTile icon={<Users className="w-5 h-5" />} label={t("Experts")} value={stats.expert_count} hint={t("Experts who submitted ratings")} color="violet" delay={120} />
                  <StatTile icon={<BarChart2 className="w-5 h-5" />} label={t("Ratings stored")} value={stats.ratings_count} hint={t("Stored rating records")} color="amber" delay={180} />
                </div>
              )}

              {/* I-CVI / S-CVI are computed from stored ratings only - no ratings, no numbers. */}
              {stats && (stats.i_cvi_pass_rate == null || stats.s_cvi_ave == null) ? (
                <Card className="p-2">
                  <EmptyState icon={<BarChart2 className="w-5 h-5" />} title={t("No ratings yet")}>
                    {t("I-CVI and S-CVI/Ave are calculated from stored expert ratings. Actual values appear after ratings are submitted.")}
                  </EmptyState>
                </Card>
              ) : stats && (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <StatTile
                    icon={<CheckCircle2 className="w-5 h-5" />}
                    label={t("I-CVI pass rate")}
                    value={`${Math.round(stats.i_cvi_pass_rate * 100)}%`}
                    hint={`${stats.rated_items} · ${t("I-CVI ≥ 0.78 threshold")}`}
                    color="emerald"
                    animate={false}
                  />
                  <StatTile
                    icon={<Award className="w-5 h-5" />}
                    label={t("S-CVI / Ave")}
                    value={stats.s_cvi_ave.toFixed(2)}
                    hint={t("Average I-CVI of rated items")}
                    color="sky"
                    animate={false}
                    delay={60}
                  />
                </div>
              )}

              {ratingConflict && <Button variant="surface" size="sm" onClick={reloadRating} disabled={queueLoading || ratingBusy}>{t("Discard draft and load latest rating")}</Button>}
              {ratingError && <ErrorBanner>{t("Rating not saved:")} {ratingError}</ErrorBanner>}

              {ratingSaved && (
                <div className="bg-success/10 border border-success/30 p-3.5 rounded-xl text-xs text-success font-mono font-bold flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 shrink-0" />
                  {t("Saved:")} {ratingSaved.item_id}
                  {ratingSaved.i_cvi != null && ` · I-CVI ${Number(ratingSaved.i_cvi).toFixed(2)}`}
                </div>
              )}

              {!items.length ? (
                <Card className="p-2">
                  <EmptyState icon={<ClipboardList className="w-5 h-5" />} title={t("No items to review")}>
                    {t(allItems.length ? 'No items in this work list. Choose More to review other items.' : 'There are no items in the question bank yet.')}
                  </EmptyState>
                </Card>
              ) : activeItem && (
                <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
                  {/* Left: the item exactly as the bank stores it */}
                  <div className="lg:col-span-7 space-y-4">
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-xs font-mono font-bold text-on-surface-variant">
                        {t("Item")} {itemIndex + 1} / {items.length}
                      </span>
                      <div className="flex items-center gap-2">
                        <Button variant="surface" size="sm" disabled={ratingBusy || itemIndex === 0} onClick={() => setActiveItemIndex(Math.max(0, itemIndex - 1))}>
                          <ChevronLeft className="w-3.5 h-3.5" /> {t("Previous")}
                        </Button>
                        <Button variant="surface" size="sm" disabled={ratingBusy || itemIndex >= items.length - 1} onClick={() => setActiveItemIndex(Math.min(items.length - 1, itemIndex + 1))}>
                          {t("Next")} <ChevronRight className="w-3.5 h-3.5" />
                        </Button>
                      </div>
                    </div>

                    <Card className="p-5 space-y-4">
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge tone="primary">{examLabel(activeItem.exam_type)}</Badge>
                        <Badge tone="secondary">{activeItem.type}</Badge>
                        <Badge tone={activeItem.ratings_count ? 'success' : 'neutral'}>{activeItem.ratings_count} {t("ratings")}</Badge>
                        {activeItem.my_rating && <Badge tone="xp">{t("You rated this")}</Badge>}
                        <span className="ml-auto text-[10px] font-mono text-on-surface-variant">{activeItem.id}</span>
                      </div>

                      <div className="space-y-1">
                        <h2 className="text-base font-bold font-display text-on-surface leading-snug" lang={contentLanguage(activeItem.title)}>{activeItem.title}</h2>
                        <p className="text-xs text-on-surface-variant" lang={contentLanguage(activeItem.chapter)}>{activeItem.chapter}</p>
                      </div>

                      <p className="text-sm text-on-surface font-medium leading-relaxed" lang={contentLanguage(activeItem.question_text)}>{activeItem.question_text}</p>

                      {activeItem.options?.length > 0 && (
                        <ul className="space-y-1.5">
                          {activeItem.options.map((opt) => (
                            <li key={opt.id} className="flex items-start gap-2 text-xs text-on-surface bg-surface-container-high rounded-xl px-3 py-2 border border-outline-variant/30">
                              <span className="font-mono font-extrabold text-primary uppercase shrink-0">{opt.id}.</span>
                              <span className="leading-relaxed" lang={contentLanguage(opt.text)}>{opt.text}</span>
                            </li>
                          ))}
                        </ul>
                      )}

                      {activeItem.code_snippet && <CodeBlock>{activeItem.code_snippet}</CodeBlock>}

                      {activeItem.curriculum_ref && (
                        <div className="flex items-center gap-1.5 text-[11px] font-mono text-on-surface-variant border-t border-outline-variant/20 pt-3">
                          <BookOpen className="w-3.5 h-3.5 text-primary shrink-0" /> <span lang={contentLanguage(activeItem.curriculum_ref)}>{activeItem.curriculum_ref}</span>
                        </div>
                      )}
                    </Card>
                  </div>

                  {/* Right: 5-criterion CVI rubric */}
                  <SectionCard headingAs="h2"
                    icon={<Sliders className="w-4 h-4 text-primary" />}
                    title={t("Content validity rubric")}
                    subtitle={t("Content validity rubric (1-4 scale)")}
                    className="lg:col-span-5 h-fit"
                    bodyClass="p-5 space-y-5"
                  >
                    <div className="space-y-4">
                      {CRITERIA.map(({ key, bn, en }) => (
                        <RatingScale key={key} bn={bn} en={en} value={ratings[key]} disabled={ratingBusy} onChange={(n) => updateDraft({ ratings: { ...ratings, [key]: n } })} />
                      ))}
                    </div>

                    <div className="space-y-1.5">
                      <label htmlFor="cvi-feedback" className="text-[11px] font-bold text-on-surface uppercase tracking-wider block">
                        {t("Expert comments")}
                      </label>
                      <textarea
                        id="cvi-feedback"
                        rows="3"
                        value={cviFeedback}
                        disabled={ratingBusy}
                        onChange={(e) => updateDraft({ feedback: e.target.value })}
                        placeholder={t("Suggest improvements to wording or distractors…")}
                        className="w-full bg-surface-container-high rounded-xl p-3 text-xs text-on-surface border border-outline-variant/30 outline-none focus:border-primary"
                      />
                    </div>

                    <div className="space-y-2">
                      <Button className="w-full" size="lg" disabled={!ratingsComplete || ratingBusy} onClick={handleSubmitCviReview}>
                        {ratingBusy ? <RefreshCw className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
                        {activeItem.my_rating ? t("Update rating") : t("Submit rating")}
                      </Button>
                      {draft && <p role="status" className="text-[11px] text-warning text-center">{t("Unsaved draft · kept while this portal is open. Submit before leaving or refreshing.")}</p>}
                      {!ratingsComplete && (
                        <p className="text-[11px] text-on-surface-variant text-center">{t("Score all five criteria first")}</p>
                      )}
                    </div>
                  </SectionCard>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* TAB 2: STUDENT CODE SUBMISSION MARKING */}
      {activeTab === 'student_marking' && (
        <div className="space-y-5">
          {subsError && <ErrorBanner onRetry={loadSubmissions}>{t("Could not load submissions:")} {subsError}</ErrorBanner>}
          {!subsLoading && <WorkScope rows={submissions} scope={submissionScope} completed={gradedByMe}
            onChange={changeSubmissionScope} disabled={subsLoading || gradeBusy} />}

          {subsLoading && !submissions.length ? (
            <div className="grid lg:grid-cols-12 gap-5">
              <Skeleton className="h-96 lg:col-span-4" />
              <Skeleton className="h-96 lg:col-span-8" />
            </div>
          ) : !visibleSubmissions.length && !subsError ? (
            <Card className="p-2">
              <EmptyState icon={<UserCheck className="w-5 h-5" />} title={t("No submissions yet")}>
                {t(submissions.length ? 'No submissions in this work list. Choose More to review other submissions.' : 'Student submissions will appear here after they submit their exams.')}
              </EmptyState>
            </Card>
          ) : visibleSubmissions.length > 0 && (
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
              {/* Left: real submission rows, labelled by pseudonymous code */}
              <SectionCard headingAs="h2"
                icon={<ClipboardList className="w-4 h-4 text-primary" />}
                title={t("Submissions")}
                subtitle={`${t("Submissions")} (${visibleSubmissions.length}) · ${t("newest first")}`}
                className="lg:col-span-4 h-fit"
                bodyClass="p-3"
                action={
                  <Button variant="ghost" size="sm" aria-label={t("Refresh submissions")} aria-busy={subsLoading} onClick={loadSubmissions} disabled={subsLoading || gradeBusy}>
                    <RefreshCw aria-hidden="true" className={`w-3.5 h-3.5 ${subsLoading ? 'animate-spin' : ''}`} />
                  </Button>
                }
              >
                <div className="space-y-2 max-h-[560px] overflow-y-auto pr-1">
                  {visibleSubmissions.map((s) => (
                    <button
                      key={s.id}
                      disabled={gradeBusy || subsLoading}
                      onClick={() => setSelectedSubId(s.id)}
                      className={`w-full text-left p-3 rounded-xl border transition-colors ${
                        s.id === selectedSubId ? 'bg-primary/10 border-primary/40' : 'bg-surface-container-high border-outline-variant/30 hover:border-primary/30'
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-xs font-mono font-extrabold text-on-surface truncate">{s.student_label}</span>
                        <Badge tone={s.status === 'GRADED' ? 'success' : 'warning'}>{s.status === 'GRADED' ? t("Graded") : t("Pending")}</Badge>
                      </div>
                      <div className="text-[11px] text-on-surface-variant truncate mt-0.5">{examLabel(s.exam_type)} · {s.chapter}</div>
                      <div className="flex flex-wrap items-center gap-x-2 mt-1 text-[10px] font-mono text-on-surface-variant">
                        <span>{t("Automatic")} {t(formatScore(s.score_pct, s.grading_status))}</span>
                        {s.assigned_marks != null && <span>· {t("Marks")} {s.assigned_marks}/{s.max_marks}</span>}
                        <span>· {formatWhen(s.submitted_at)}</span>
                      </div>
                    </button>
                  ))}
                </div>
              </SectionCard>

              {/* Right: the selected submission and the marking panel */}
              <div className="lg:col-span-8 space-y-4">
                {activeSub && (
                  <>
                    <Card className="p-5 space-y-4">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="px-3 py-1 rounded-xl bg-primary/15 border border-primary/30 text-primary font-mono text-sm font-extrabold">
                              {activeSub.student_label}
                            </span>
                            <Badge tone={activeSub.status === 'GRADED' ? 'success' : 'warning'}>
                              {activeSub.status === 'GRADED' ? t("Graded") : t("Pending")}
                            </Badge>
                          </div>
                          <p className="text-[11px] text-on-surface-variant mt-1.5">
                            {activeSub.participant_code ? t("Pseudonymous participant code") : t("Username")}
                            {' · '}{t('Submission')} #{activeSub.id}
                          </p>
                        </div>
                        <div className="text-[11px] font-mono text-on-surface-variant text-right">
                          <div>{examLabel(activeSub.exam_type)}</div>
                          <div lang={contentLanguage(activeSub.chapter)}>{activeSub.chapter}</div>
                          <div>{t("Submitted:")} {formatWhen(activeSub.submitted_at)}</div>
                        </div>
                      </div>

                      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                        <StatTile icon={<BarChart2 className="w-5 h-5" />} label={t("Server score")} value={<span className={serverScore.endsWith('%') ? '' : 'block text-sm break-words'}>{serverScore}</span>} hint={t("Score verified by the server")} color="sky" animate={false} />
                        <StatTile
                          icon={<CheckCircle2 className="w-5 h-5" />}
                          label={t("Correct")}
                          value={activeSub.correct != null && activeSub.total != null ? `${activeSub.correct} / ${activeSub.total}` : '—'}
                          hint={t("Correct answers")}
                          color="emerald"
                          animate={false}
                          delay={60}
                        />
                        <StatTile
                          icon={<Award className="w-5 h-5" />}
                          label={t("Expert marks")}
                          value={activeSub.assigned_marks != null ? `${activeSub.assigned_marks} / ${activeSub.max_marks}` : t("Unassigned")}
                          hint={activeSub.graded_by ? `${t("Marked by:")} ${activeSub.graded_by}` : t("Not yet marked")}
                          color="violet"
                          animate={false}
                          delay={120}
                        />
                      </div>
                    </Card>

                    {activeSub.timing && (
                      <Card className="p-5 space-y-3">
                        <h2 className="text-sm font-bold">{t("Dates & time")}</h2>
                        <p className="text-[11px] text-on-surface-variant">{t("Dhaka time · elapsed time is calculated separately for each exam")}</p>
                        <dl className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                          {[
                            [t("Exam opened"), formatTimingDate(activeSub.timing.opened_at)],
                            [t("Submitted"), formatTimingDate(activeSub.timing.submitted_at)],
                            [t("Time spent on this exam"), formatElapsedDays(activeSub.timing.paper_elapsed_days, language)],
                            [t("Total study time"), activeSub.timing.study_completed_at ? formatElapsedDays(activeSub.timing.study_elapsed_days, language) : t("Not yet completed")],
                            [t("Study started"), formatTimingDate(activeSub.timing.study_started_at)],
                            [t("All exams completed"), formatTimingDate(activeSub.timing.study_completed_at)],
                            [t("Participation window"), activeSub.timing.window_start && activeSub.timing.window_end
                              ? `${formatTimingDate(activeSub.timing.window_start)} – ${formatTimingDate(activeSub.timing.window_end)}` : '—'],
                          ].map(([label, value]) => (
                            <div key={label} className="rounded-xl bg-surface-container-high p-3">
                              <dt className="text-on-surface-variant">{label}</dt>
                              <dd className="mt-1 font-semibold break-words">{value}</dd>
                            </div>
                          ))}
                        </dl>
                      </Card>
                    )}

                    <SectionCard headingAs="h2"
                      icon={<FileCode className="w-4 h-4 text-primary" />}
                      title={t("Submitted code")}
                      subtitle={`${t("Submitted code answers")} (${activeSub.code_answers?.length || 0})`}
                      bodyClass="p-4 space-y-4"
                    >
                      {!activeSub.code_answers?.length ? (
                        <EmptyState icon={<FileCode className="w-5 h-5" />} title={t("No code answers")}>
                          {t("No coding answers were found in this submission.")}
                        </EmptyState>
                      ) : (
                        activeSub.code_answers.map((ca) => (
                          <div key={ca.item_id} className="space-y-2.5 border-b border-outline-variant/20 last:border-0 pb-4 last:pb-0">
                            <div className="flex items-start justify-between gap-3">
                              <div className="min-w-0">
                                <h3 className="text-xs font-extrabold text-on-surface" lang={contentLanguage(ca.title || ca.item_id)}>{ca.title || ca.item_id}</h3>
                                {ca.question && <p className="text-[11px] text-on-surface-variant leading-relaxed mt-1" lang={contentLanguage(ca.question)}>{ca.question}</p>}
                              </div>
                              <Badge tone={autoTone(ca.auto?.status)} className="shrink-0">{ca.auto?.status || 'NOT RUN'}</Badge>
                            </div>

                            {ca.auto && (
                              <div className="text-[11px] font-mono text-on-surface-variant bg-surface-container-high rounded-xl px-3 py-2 border border-outline-variant/30">
                                {ca.auto.total_tests != null && <span className="font-bold text-on-surface">{ca.auto.passed_count ?? 0}/{ca.auto.total_tests} {t("tests passed")}</span>}
                                {ca.auto.detail && <span className="block mt-0.5" lang={contentLanguage(ca.auto.detail)}>{ca.auto.detail}</span>}
                              </div>
                            )}

                            <CodeBlock>{ca.code || t("(No code submitted)")}</CodeBlock>
                          </div>
                        ))
                      )}
                    </SectionCard>

                    <SectionCard headingAs="h2"
                      icon={<Award className="w-4 h-4 text-primary" />}
                      title={t("Marks & feedback")}
                      subtitle={t("Expert marks & feedback")}
                      bodyClass="p-5 space-y-5"
                    >
                      {gradeConflict && <Button variant="surface" size="sm" onClick={reloadGrade} disabled={subsLoading || gradeBusy}>{t("Load latest marks (discard edits)")}</Button>}
                      {gradeError && <ErrorBanner>{t("Not saved:")} {t(gradeError)}</ErrorBanner>}

                      {gradeSaved && (
                        <div className="bg-success/10 border border-success/30 p-3.5 rounded-xl text-xs text-success font-mono font-bold flex items-center gap-2">
                          <CheckCircle2 className="w-4 h-4 shrink-0" />
                          {t("Saved:")} {t("Submission")} #{gradeSaved.submission_id} · {gradeSaved.assigned_marks} / {gradeSaved.max_marks} · {formatWhen(gradeSaved.graded_at)}
                        </div>
                      )}

                      <div className="space-y-2">
                        <label htmlFor="assigned-marks" className="text-xs font-extrabold text-on-surface uppercase tracking-wider flex justify-between gap-2">
                          <span>{t("Assigned marks")}</span>
                          <span className="text-primary font-mono text-sm">
                            {assignedMarks === '' ? t("Unassigned") : `${assignedMarks} / ${activeSub.max_marks ?? 100}`}
                          </span>
                        </label>
                        <input
                          id="assigned-marks"
                          type="number"
                          min="0"
                          max="100"
                          step="1"
                          disabled={gradeBusy || subsLoading}
                          value={assignedMarks}
                          onChange={(e) => updateGradeDraft({ marks: e.target.value })}
                          placeholder="0 - 100"
                          className="w-full bg-surface-container-high rounded-xl p-3.5 text-base text-on-surface font-mono font-extrabold border border-outline-variant/30 outline-none focus:border-primary shadow-sm"
                        />
                      </div>

                      <div className="space-y-2">
                        <label htmlFor="teacher-feedback" className="text-xs font-extrabold text-on-surface uppercase tracking-wider block">
                          {t("Qualitative feedback")}
                        </label>
                        <textarea
                          id="teacher-feedback"
                          rows="4"
                          value={teacherFeedback}
                          disabled={gradeBusy || subsLoading}
                          onChange={(e) => updateGradeDraft({ feedback: e.target.value })}
                          placeholder={t("Write feedback on loop conditions, logic and code style…")}
                          className="w-full bg-surface-container-high rounded-xl p-3.5 text-xs text-on-surface font-medium border border-outline-variant/30 outline-none focus:border-primary shadow-sm"
                        />
                      </div>

                      <Button className="w-full" size="lg" disabled={gradeBusy || subsLoading} onClick={handleGradeSubmission}>
                        {gradeBusy ? <RefreshCw className="w-4 h-4 animate-spin" /> : <CheckSquare className="w-4 h-4" />}
                        {t("Save marks")}
                      </Button>
                      {gradeDraft && <p role="status" className="text-[11px] text-warning">{t("Unsaved draft · kept while this portal is open. Save before leaving or refreshing.")}</p>}
                    </SectionCard>
                  </>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
