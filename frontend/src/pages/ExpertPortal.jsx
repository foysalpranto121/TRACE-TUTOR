import { useState, useEffect } from 'react';
import { apiService } from '../services/api';
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
const EXAM_LABELS = {
  pre: 'প্রি-টেস্ট (pre)',
  post: 'পোস্ট-টেস্ট (post)',
  transfer: 'ট্রান্সফার (transfer)',
  withdrawal: 'উইথড্রয়াল (withdrawal)',
};

const examLabel = (t) => EXAM_LABELS[t] || t || '—';
const autoTone = (status) => (status === 'SUCCESS' ? 'success' : status ? 'danger' : 'neutral');

const formatWhen = (iso) => {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString([], { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
};

const CodeBlock = ({ children }) => (
  <div className="bg-surface-container-lowest p-4 rounded-xl border border-outline-variant/30 overflow-x-auto shadow-inner">
    <pre className="font-mono text-xs text-primary leading-relaxed whitespace-pre-wrap">{children}</pre>
  </div>
);

const ErrorBanner = ({ children, onRetry }) => (
  <div className="bg-danger/10 border border-danger/30 rounded-xl p-4 text-xs text-danger flex flex-wrap items-center gap-3">
    <AlertTriangle className="w-4 h-4 shrink-0" />
    <span className="flex-1 min-w-0">{children}</span>
    {onRetry && <Button variant="surface" size="sm" onClick={onRetry}><RefreshCw className="w-3.5 h-3.5" /> আবার চেষ্টা করুন (Retry)</Button>}
  </div>
);

// 1-4 buttons rather than a slider: a slider always carries a value, so an untouched
// rubric would silently submit a default score the expert never chose.
const RatingScale = ({ bn, en, value, onChange }) => (
  <div className="space-y-1.5">
    <div className="flex items-baseline justify-between gap-2">
      <span className="text-xs font-bold text-on-surface">
        {bn} <span className="font-medium text-on-surface-variant">({en})</span>
      </span>
      <span className="text-[10px] font-mono font-bold text-on-surface-variant shrink-0">{value ? `${value} / 4` : 'অনির্ধারিত'}</span>
    </div>
    <div className="grid grid-cols-4 gap-1.5">
      {[1, 2, 3, 4].map((n) => (
        <button
          key={n}
          type="button"
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

export const ExpertPortal = () => {
  const [activeTab, setActiveTab] = useState('cvi_certification'); // 'cvi_certification' or 'student_marking'

  // Tab 1: CVI certification
  const [reviewData, setReviewData] = useState(null);
  const [queueLoading, setQueueLoading] = useState(true);
  const [queueError, setQueueError] = useState(null);
  const [activeItemIndex, setActiveItemIndex] = useState(0);
  const [ratings, setRatings] = useState(BLANK_RATINGS);
  const [cviFeedback, setCviFeedback] = useState('');
  const [ratingBusy, setRatingBusy] = useState(false);
  const [ratingError, setRatingError] = useState(null);
  const [ratingSaved, setRatingSaved] = useState(null);

  // Tab 2: student submission marking
  const [submissions, setSubmissions] = useState([]);
  const [subsLoading, setSubsLoading] = useState(true);
  const [subsError, setSubsError] = useState(null);
  const [selectedSubId, setSelectedSubId] = useState(null);
  const [assignedMarks, setAssignedMarks] = useState('');
  const [teacherFeedback, setTeacherFeedback] = useState('');
  const [gradeBusy, setGradeBusy] = useState(false);
  const [gradeError, setGradeError] = useState(null);
  const [gradeSaved, setGradeSaved] = useState(null);

  const loadQueue = async () => {
    setQueueLoading(true);
    setQueueError(null);
    try {
      const data = await apiService.getExpertQueue();
      setReviewData(data);
      return data;
    } catch (err) {
      setQueueError(err.message);
      return null;
    } finally {
      setQueueLoading(false);
    }
  };

  const loadSubmissions = async () => {
    setSubsLoading(true);
    setSubsError(null);
    try {
      const data = await apiService.getStudentSubmissions();
      const rows = data.submissions || [];
      setSubmissions(rows);
      setSelectedSubId((prev) => (rows.some((s) => s.id === prev) ? prev : rows[0]?.id ?? null));
    } catch (err) {
      setSubsError(err.message);
    } finally {
      setSubsLoading(false);
    }
  };

  useEffect(() => {
    loadQueue();
    loadSubmissions();
  }, []);

  const items = reviewData?.items_to_review || [];
  const stats = reviewData?.cvi_stats;
  const activeItem = items[activeItemIndex];
  const activeSub = submissions.find((s) => s.id === selectedSubId) || null;

  // Re-rating edits this expert's stored row, so open the form on what they already submitted.
  useEffect(() => {
    const mine = activeItem?.my_rating;
    setRatings(mine ? Object.fromEntries(CRITERIA.map(({ key }) => [key, mine[key] ?? null])) : BLANK_RATINGS);
    setCviFeedback(mine?.feedback || '');
    setRatingError(null);
  }, [activeItem?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // An ungraded submission starts empty - a pre-filled mark would anchor the grader.
  useEffect(() => {
    setAssignedMarks(activeSub?.assigned_marks ?? '');
    setTeacherFeedback(activeSub?.feedback || '');
    setGradeError(null);
    setGradeSaved(null);
  }, [selectedSubId]); // eslint-disable-line react-hooks/exhaustive-deps

  const ratingsComplete = CRITERIA.every(({ key }) => ratings[key]);

  const handleSubmitCviReview = async () => {
    if (!activeItem || !ratingsComplete) return;
    setRatingBusy(true);
    setRatingError(null);
    setRatingSaved(null);
    try {
      const res = await apiService.submitExpertRating(activeItem.id, ratings, cviFeedback);
      setRatingSaved(res);
      // CVI is recomputed server-side from the stored rows, so re-read it instead of guessing.
      const fresh = await loadQueue();
      const total = fresh?.items_to_review?.length ?? items.length;
      setActiveItemIndex((prev) => Math.min(prev + 1, Math.max(0, total - 1)));
    } catch (err) {
      setRatingError(err.message);
    } finally {
      setRatingBusy(false);
    }
  };

  const handleGradeSubmission = async () => {
    if (!activeSub) return;
    const marks = Number(assignedMarks);
    if (assignedMarks === '' || Number.isNaN(marks)) {
      setGradeError('নম্বর লিখুন — ০ থেকে ১০০ (enter a mark from 0 to 100).');
      return;
    }
    setGradeBusy(true);
    setGradeError(null);
    setGradeSaved(null);
    try {
      const res = await apiService.gradeSubmission(activeSub.id, marks, teacherFeedback);
      setGradeSaved(res);
      await loadSubmissions(); // status and graded_by come back from the server, never assumed here
    } catch (err) {
      setGradeError(err.message);
    } finally {
      setGradeBusy(false);
    }
  };

  return (
    <div className="max-w-7xl mx-auto w-full space-y-5 pb-10">
      {/* Header & tab selector */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-outline-variant/20 pb-4">
        <div>
          <h1 className="text-2xl font-extrabold font-display text-on-surface flex items-center gap-2">
            <Brain className="w-7 h-7 text-primary" /> এক্সপার্ট ওয়ার্কবেঞ্চ
          </h1>
          <p className="text-xs text-on-surface-variant font-medium">
            প্রশ্ন ব্যাংক সার্টিফিকেশন ও শিক্ষার্থীর কোড মূল্যায়ন (Item certification &amp; student code marking)
          </p>
        </div>

        <div className="flex items-center gap-1 bg-surface-container p-1 rounded-xl border border-outline-variant/30 text-xs font-semibold shadow-sm">
          <button
            onClick={() => setActiveTab('cvi_certification')}
            className={`px-4 py-2 rounded-lg transition-all flex items-center gap-2 ${
              activeTab === 'cvi_certification' ? 'bg-primary text-on-primary font-bold shadow-sm' : 'text-on-surface-variant hover:text-on-surface'
            }`}
          >
            <Sliders className="w-4 h-4" /> CVI সার্টিফিকেশন ({items.length})
          </button>
          <button
            onClick={() => setActiveTab('student_marking')}
            className={`px-4 py-2 rounded-lg transition-all flex items-center gap-2 ${
              activeTab === 'student_marking' ? 'bg-primary text-on-primary font-bold shadow-sm' : 'text-on-surface-variant hover:text-on-surface'
            }`}
          >
            <UserCheck className="w-4 h-4" /> কোড মূল্যায়ন ({submissions.length})
          </button>
        </div>
      </div>

      {/* TAB 1: QUESTION BANK CVI CERTIFICATION */}
      {activeTab === 'cvi_certification' && (
        <div className="space-y-5">
          {queueError && <ErrorBanner onRetry={loadQueue}>রিভিউ কিউ লোড করা যায়নি (could not load the review queue): {queueError}</ErrorBanner>}

          {queueLoading && !reviewData ? (
            <div className="space-y-4">
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-24" />)}</div>
              <div className="grid lg:grid-cols-12 gap-5"><Skeleton className="h-96 lg:col-span-7" /><Skeleton className="h-96 lg:col-span-5" /></div>
            </div>
          ) : reviewData && (
            <>
              {stats && (
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                  <StatTile icon={<ClipboardList className="w-5 h-5" />} label="Items in bank" value={stats.total_items} hint="ব্যাংকের মোট আইটেম" color="sky" />
                  <StatTile icon={<CheckSquare className="w-5 h-5" />} label="Rated items" value={stats.rated_items} hint="রেটিং পাওয়া আইটেম" color="emerald" delay={60} />
                  <StatTile icon={<Users className="w-5 h-5" />} label="Experts" value={stats.expert_count} hint="রেটিংদাতা এক্সপার্ট" color="violet" delay={120} />
                  <StatTile icon={<BarChart2 className="w-5 h-5" />} label="Ratings stored" value={stats.ratings_count} hint="সংরক্ষিত রেটিং সারি" color="amber" delay={180} />
                </div>
              )}

              {/* I-CVI / S-CVI are computed from stored ratings only - no ratings, no numbers. */}
              {stats && (stats.i_cvi_pass_rate == null || stats.s_cvi_ave == null) ? (
                <Card className="p-2">
                  <EmptyState icon={<BarChart2 className="w-5 h-5" />} title="এখনো কোনো রেটিং নেই (No ratings yet)">
                    I-CVI ও S-CVI/Ave কেবল সংরক্ষিত এক্সপার্ট রেটিং থেকে হিসাব হয়। রেটিং জমা পড়লে এখানে প্রকৃত মান দেখা যাবে।
                  </EmptyState>
                </Card>
              ) : stats && (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <StatTile
                    icon={<CheckCircle2 className="w-5 h-5" />}
                    label="I-CVI pass rate"
                    value={`${Math.round(stats.i_cvi_pass_rate * 100)}%`}
                    hint={`${stats.rated_items} আইটেমের মধ্যে I-CVI ≥ 0.78 (threshold)`}
                    color="emerald"
                    animate={false}
                  />
                  <StatTile
                    icon={<Award className="w-5 h-5" />}
                    label="S-CVI / Ave"
                    value={stats.s_cvi_ave.toFixed(2)}
                    hint="রেটিং পাওয়া আইটেমগুলোর গড় I-CVI"
                    color="sky"
                    animate={false}
                    delay={60}
                  />
                </div>
              )}

              {ratingError && <ErrorBanner>রেটিং সংরক্ষণ করা যায়নি (rating not saved): {ratingError}</ErrorBanner>}

              {ratingSaved && (
                <div className="bg-success/10 border border-success/30 p-3.5 rounded-xl text-xs text-success font-mono font-bold flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 shrink-0" />
                  সংরক্ষিত (saved): {ratingSaved.item_id}
                  {ratingSaved.i_cvi != null && ` · I-CVI ${Number(ratingSaved.i_cvi).toFixed(2)}`}
                </div>
              )}

              {!items.length ? (
                <Card className="p-2">
                  <EmptyState icon={<ClipboardList className="w-5 h-5" />} title="রিভিউ করার মতো কোনো আইটেম নেই (No items to review)">
                    প্রশ্ন ব্যাংকে এখনো কোনো আইটেম পাওয়া যায়নি।
                  </EmptyState>
                </Card>
              ) : activeItem && (
                <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
                  {/* Left: the item exactly as the bank stores it */}
                  <div className="lg:col-span-7 space-y-4">
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-xs font-mono font-bold text-on-surface-variant">
                        আইটেম {activeItemIndex + 1} / {items.length}
                      </span>
                      <div className="flex items-center gap-2">
                        <Button variant="surface" size="sm" disabled={activeItemIndex === 0} onClick={() => setActiveItemIndex((i) => Math.max(0, i - 1))}>
                          <ChevronLeft className="w-3.5 h-3.5" /> আগের
                        </Button>
                        <Button variant="surface" size="sm" disabled={activeItemIndex >= items.length - 1} onClick={() => setActiveItemIndex((i) => Math.min(items.length - 1, i + 1))}>
                          পরের <ChevronRight className="w-3.5 h-3.5" />
                        </Button>
                      </div>
                    </div>

                    <Card className="p-5 space-y-4">
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge tone="primary">{examLabel(activeItem.exam_type)}</Badge>
                        <Badge tone="secondary">{activeItem.type}</Badge>
                        <Badge tone={activeItem.ratings_count ? 'success' : 'neutral'}>{activeItem.ratings_count} রেটিং</Badge>
                        {activeItem.my_rating && <Badge tone="xp">আপনার রেটিং আছে (you rated this)</Badge>}
                        <span className="ml-auto text-[10px] font-mono text-on-surface-variant">{activeItem.id}</span>
                      </div>

                      <div className="space-y-1">
                        <h3 className="text-base font-bold font-display text-on-surface leading-snug">{activeItem.title}</h3>
                        <p className="text-xs text-on-surface-variant">{activeItem.chapter}</p>
                      </div>

                      <p className="text-sm text-on-surface font-medium leading-relaxed">{activeItem.question_text}</p>

                      {activeItem.options?.length > 0 && (
                        <ul className="space-y-1.5">
                          {activeItem.options.map((opt) => (
                            <li key={opt.id} className="flex items-start gap-2 text-xs text-on-surface bg-surface-container-high rounded-xl px-3 py-2 border border-outline-variant/30">
                              <span className="font-mono font-extrabold text-primary uppercase shrink-0">{opt.id}.</span>
                              <span className="leading-relaxed">{opt.text}</span>
                            </li>
                          ))}
                        </ul>
                      )}

                      {activeItem.code_snippet && <CodeBlock>{activeItem.code_snippet}</CodeBlock>}

                      {activeItem.curriculum_ref && (
                        <div className="flex items-center gap-1.5 text-[11px] font-mono text-on-surface-variant border-t border-outline-variant/20 pt-3">
                          <BookOpen className="w-3.5 h-3.5 text-primary shrink-0" /> {activeItem.curriculum_ref}
                        </div>
                      )}
                    </Card>
                  </div>

                  {/* Right: 5-criterion CVI rubric */}
                  <SectionCard
                    icon={<Sliders className="w-4 h-4 text-primary" />}
                    title="কনটেন্ট ভ্যালিডিটি রুব্রিক"
                    subtitle="Content validity rubric (1-4 scale)"
                    className="lg:col-span-5 h-fit"
                    bodyClass="p-5 space-y-5"
                  >
                    <div className="space-y-4">
                      {CRITERIA.map(({ key, bn, en }) => (
                        <RatingScale key={key} bn={bn} en={en} value={ratings[key]} onChange={(n) => setRatings((prev) => ({ ...prev, [key]: n }))} />
                      ))}
                    </div>

                    <div className="space-y-1.5">
                      <label htmlFor="cvi-feedback" className="text-[11px] font-bold text-on-surface uppercase tracking-wider block">
                        এক্সপার্ট মন্তব্য (Expert comments)
                      </label>
                      <textarea
                        id="cvi-feedback"
                        rows="3"
                        value={cviFeedback}
                        onChange={(e) => setCviFeedback(e.target.value)}
                        placeholder="শব্দচয়ন বা ডিস্ট্র্যাক্টর সংশোধনের প্রস্তাব..."
                        className="w-full bg-surface-container-high rounded-xl p-3 text-xs text-on-surface border border-outline-variant/30 outline-none focus:border-primary"
                      />
                    </div>

                    <div className="space-y-2">
                      <Button className="w-full" size="lg" disabled={!ratingsComplete || ratingBusy} onClick={handleSubmitCviReview}>
                        {ratingBusy ? <RefreshCw className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
                        {activeItem.my_rating ? 'রেটিং হালনাগাদ করুন (Update)' : 'রেটিং জমা দিন (Submit)'}
                      </Button>
                      {!ratingsComplete && (
                        <p className="text-[11px] text-on-surface-variant text-center">পাঁচটি মানদণ্ডেই স্কোর দিন (score all five criteria first)</p>
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
          {subsError && <ErrorBanner onRetry={loadSubmissions}>সাবমিশন লোড করা যায়নি (could not load submissions): {subsError}</ErrorBanner>}

          {subsLoading && !submissions.length ? (
            <div className="grid lg:grid-cols-12 gap-5">
              <Skeleton className="h-96 lg:col-span-4" />
              <Skeleton className="h-96 lg:col-span-8" />
            </div>
          ) : !submissions.length && !subsError ? (
            <Card className="p-2">
              <EmptyState icon={<UserCheck className="w-5 h-5" />} title="এখনো কোনো সাবমিশন নেই (No submissions yet)">
                শিক্ষার্থীরা পরীক্ষা জমা দিলে সেগুলো এখানে দেখা যাবে।
              </EmptyState>
            </Card>
          ) : submissions.length > 0 && (
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
              {/* Left: real submission rows, labelled by pseudonymous code */}
              <SectionCard
                icon={<ClipboardList className="w-4 h-4 text-primary" />}
                title="সাবমিশন"
                subtitle={`Submissions (${submissions.length}) - newest first`}
                className="lg:col-span-4 h-fit"
                bodyClass="p-3"
                action={
                  <Button variant="ghost" size="sm" onClick={loadSubmissions} disabled={subsLoading}>
                    <RefreshCw className={`w-3.5 h-3.5 ${subsLoading ? 'animate-spin' : ''}`} />
                  </Button>
                }
              >
                <div className="space-y-2 max-h-[560px] overflow-y-auto pr-1">
                  {submissions.map((s) => (
                    <button
                      key={s.id}
                      onClick={() => setSelectedSubId(s.id)}
                      className={`w-full text-left p-3 rounded-xl border transition-colors ${
                        s.id === selectedSubId ? 'bg-primary/10 border-primary/40' : 'bg-surface-container-high border-outline-variant/30 hover:border-primary/30'
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-xs font-mono font-extrabold text-on-surface truncate">{s.student_label}</span>
                        <Badge tone={s.status === 'GRADED' ? 'success' : 'warning'}>{s.status === 'GRADED' ? 'মূল্যায়িত' : 'অপেক্ষমাণ'}</Badge>
                      </div>
                      <div className="text-[11px] text-on-surface-variant truncate mt-0.5">{examLabel(s.exam_type)} · {s.chapter}</div>
                      <div className="flex flex-wrap items-center gap-x-2 mt-1 text-[10px] font-mono text-on-surface-variant">
                        <span>স্বয়ংক্রিয় {s.score_pct}%</span>
                        {s.assigned_marks != null && <span>· নম্বর {s.assigned_marks}/{s.max_marks}</span>}
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
                              {activeSub.status === 'GRADED' ? 'মূল্যায়িত (graded)' : 'অপেক্ষমাণ (pending)'}
                            </Badge>
                          </div>
                          <p className="text-[11px] text-on-surface-variant mt-1.5">
                            {activeSub.participant_code ? 'ছদ্মনাম অংশগ্রহণকারী কোড (pseudonymous participant code)' : 'ব্যবহারকারী নাম (username)'}
                            {' · '}সাবমিশন #{activeSub.id}
                          </p>
                        </div>
                        <div className="text-[11px] font-mono text-on-surface-variant text-right">
                          <div>{examLabel(activeSub.exam_type)}</div>
                          <div>{activeSub.chapter}</div>
                          <div>জমা: {formatWhen(activeSub.submitted_at)}</div>
                        </div>
                      </div>

                      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                        <StatTile icon={<BarChart2 className="w-5 h-5" />} label="Server score" value={`${activeSub.score_pct}%`} hint="সার্ভারে যাচাই করা স্কোর" color="sky" animate={false} />
                        <StatTile
                          icon={<CheckCircle2 className="w-5 h-5" />}
                          label="Correct"
                          value={activeSub.correct != null && activeSub.total != null ? `${activeSub.correct} / ${activeSub.total}` : '—'}
                          hint="সঠিক উত্তর"
                          color="emerald"
                          animate={false}
                          delay={60}
                        />
                        <StatTile
                          icon={<Award className="w-5 h-5" />}
                          label="Expert marks"
                          value={activeSub.assigned_marks != null ? `${activeSub.assigned_marks} / ${activeSub.max_marks}` : 'অনির্ধারিত'}
                          hint={activeSub.graded_by ? `মূল্যায়ন: ${activeSub.graded_by}` : 'এখনো মূল্যায়ন হয়নি'}
                          color="violet"
                          animate={false}
                          delay={120}
                        />
                      </div>
                    </Card>

                    <SectionCard
                      icon={<FileCode className="w-4 h-4 text-primary" />}
                      title="জমা দেওয়া কোড"
                      subtitle={`Submitted code answers (${activeSub.code_answers?.length || 0})`}
                      bodyClass="p-4 space-y-4"
                    >
                      {!activeSub.code_answers?.length ? (
                        <EmptyState icon={<FileCode className="w-5 h-5" />} title="কোনো কোড উত্তর নেই (No code answers)">
                          এই সাবমিশনে কোডিং আইটেমের উত্তর পাওয়া যায়নি।
                        </EmptyState>
                      ) : (
                        activeSub.code_answers.map((ca) => (
                          <div key={ca.item_id} className="space-y-2.5 border-b border-outline-variant/20 last:border-0 pb-4 last:pb-0">
                            <div className="flex items-start justify-between gap-3">
                              <div className="min-w-0">
                                <h4 className="text-xs font-extrabold text-on-surface">{ca.title || ca.item_id}</h4>
                                {ca.question && <p className="text-[11px] text-on-surface-variant leading-relaxed mt-1">{ca.question}</p>}
                              </div>
                              <Badge tone={autoTone(ca.auto?.status)} className="shrink-0">{ca.auto?.status || 'NOT RUN'}</Badge>
                            </div>

                            {ca.auto && (
                              <div className="text-[11px] font-mono text-on-surface-variant bg-surface-container-high rounded-xl px-3 py-2 border border-outline-variant/30">
                                {ca.auto.total_tests != null && <span className="font-bold text-on-surface">{ca.auto.passed_count ?? 0}/{ca.auto.total_tests} টেস্ট পাস</span>}
                                {ca.auto.detail && <span className="block mt-0.5">{ca.auto.detail}</span>}
                              </div>
                            )}

                            <CodeBlock>{ca.code || '(কোনো কোড জমা পড়েনি — no code submitted)'}</CodeBlock>
                          </div>
                        ))
                      )}
                    </SectionCard>

                    <SectionCard
                      icon={<Award className="w-4 h-4 text-primary" />}
                      title="নম্বর ও মতামত"
                      subtitle="Expert marks & feedback"
                      bodyClass="p-5 space-y-5"
                    >
                      {gradeError && <ErrorBanner>সংরক্ষণ করা যায়নি (not saved): {gradeError}</ErrorBanner>}

                      {gradeSaved && (
                        <div className="bg-success/10 border border-success/30 p-3.5 rounded-xl text-xs text-success font-mono font-bold flex items-center gap-2">
                          <CheckCircle2 className="w-4 h-4 shrink-0" />
                          সংরক্ষিত (saved): সাবমিশন #{gradeSaved.submission_id} · {gradeSaved.assigned_marks} / {gradeSaved.max_marks} · {formatWhen(gradeSaved.graded_at)}
                        </div>
                      )}

                      <div className="space-y-2">
                        <label htmlFor="assigned-marks" className="text-xs font-extrabold text-on-surface uppercase tracking-wider flex justify-between gap-2">
                          <span>প্রদত্ত নম্বর (Assigned marks)</span>
                          <span className="text-primary font-mono text-sm">
                            {assignedMarks === '' ? 'অনির্ধারিত' : `${assignedMarks} / ${activeSub.max_marks ?? 100}`}
                          </span>
                        </label>
                        <input
                          id="assigned-marks"
                          type="number"
                          min="0"
                          max="100"
                          value={assignedMarks}
                          onChange={(e) => setAssignedMarks(e.target.value)}
                          placeholder="0 - 100"
                          className="w-full bg-surface-container-high rounded-xl p-3.5 text-base text-on-surface font-mono font-extrabold border border-outline-variant/30 outline-none focus:border-primary shadow-sm"
                        />
                      </div>

                      <div className="space-y-2">
                        <label htmlFor="teacher-feedback" className="text-xs font-extrabold text-on-surface uppercase tracking-wider block">
                          গুণগত মতামত (Qualitative feedback)
                        </label>
                        <textarea
                          id="teacher-feedback"
                          rows="4"
                          value={teacherFeedback}
                          onChange={(e) => setTeacherFeedback(e.target.value)}
                          placeholder="লুপের শর্ত, লজিক ও কোড স্টাইল নিয়ে মতামত লিখুন..."
                          className="w-full bg-surface-container-high rounded-xl p-3.5 text-xs text-on-surface font-medium border border-outline-variant/30 outline-none focus:border-primary shadow-sm"
                        />
                      </div>

                      <Button className="w-full" size="lg" disabled={gradeBusy} onClick={handleGradeSubmission}>
                        {gradeBusy ? <RefreshCw className="w-4 h-4 animate-spin" /> : <CheckSquare className="w-4 h-4" />}
                        নম্বর সংরক্ষণ করুন (Save marks)
                      </Button>
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
