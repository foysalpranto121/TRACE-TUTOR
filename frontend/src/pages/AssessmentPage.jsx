import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { apiService } from '../services/api';
import { useAuth } from '../context/useAuth';
import {
  FileCheck,
  CheckCircle2,
  ArrowRight,
  ShieldAlert,
  Award,
  RefreshCw,
  BookOpen,
  Code,
  Database,
  Globe,
  Bot,
  Sparkles,
  Send,
  Lightbulb,
  Lock,
  User,
  Terminal,
  Trash2,
  Play,
  Loader2,
  XCircle,
  AlertCircle,
  ArrowRightLeft
} from 'lucide-react';
import { Button, Badge } from '../components/ui';

// Grading runs on the server after the answers are saved; poll at this cadence, and give
// up waiting (never resubmit - the answers are already stored) after this long.
const GRADING_POLL_MS = 1500;
const GRADING_POLL_MAX_MS = 6000;
const GRADING_WAIT_LIMIT_MS = 3 * 60 * 1000;

const CHAPTER_FILTERS = {
  CHAP4: 'Chapter 4',
  CHAP5: 'Chapter 5',
  CHAP6: 'Chapter 6',
};

// Protocol order. The server decides which of these a given caller may actually open
// (assessment/views.py); this list only drives the tab strip.
const EXAM_TABS = [
  { type: 'pre', label: 'Pre-Test (Baseline)', activeClass: 'bg-primary text-on-primary' },
  { type: 'post', label: 'Post-Test (+AI Tutor)', activeClass: 'bg-primary text-on-primary' },
  { type: 'transfer', label: 'Transfer Test (+AI Tutor)', activeClass: 'bg-primary text-on-primary' },
  { type: 'withdrawal', label: 'Withdrawal Task (No AI)', activeClass: 'bg-amber-500 text-on-surface' },
];

const PHASE_LABEL = {
  post: 'Post-Test',
  transfer: 'Transfer Test',
};

/**
 * The opening message in the tutor panel.
 *
 * Plain text only, and deliberately so. This used to ship a hardcoded `rag_answer` -
 * an invented textbook rule with an invented "NCTB Board Textbook - Chapter 5"
 * citation - rendered in the same panel as genuine retrieved answers, in the arm where
 * tutor access is the manipulation. Every participant saw the same fabricated citation
 * regardless of the chapter they were working in. Nothing in this panel may claim a
 * curriculum source that retrieval did not actually return.
 */
const welcomeMessage = (examType, cleared = false) => ({
  sender: 'ai',
  text: cleared
    ? 'Chat history cleared. Ask a question about this task and I will answer from the NCTB textbook passages I retrieve, alongside my own reasoning.'
    : `TRACE Tutor is available during the ${PHASE_LABEL[examType] || 'assessment'}. `
      + 'Ask about a concept, an error or your code. Each answer shows the NCTB textbook '
      + 'passage it is grounded in, with its page citation, next to independent reasoning.',
  time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
});

export const AssessmentPage = () => {
  const { language } = useAuth();
  const [examType, setExamType] = useState('pre'); // 'pre', 'post', 'transfer', 'withdrawal'
  // Which papers this participant may open, as reported by the server.
  const [availableExams, setAvailableExams] = useState(['pre']);
  const [selectedChapter, setSelectedChapter] = useState('ALL'); // 'ALL', 'CHAP4', 'CHAP5', 'CHAP6'
  const [allItems, setAllItems] = useState([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [selectedAnswers, setSelectedAnswers] = useState({});
  const [userCodeAnswers, setUserCodeAnswers] = useState({});
  const [isSubmitted, setIsSubmitted] = useState(false);
  const [scoreResult, setScoreResult] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  // Server-side grading state of the submitted form: null | 'pending' | 'grading' | 'graded' | 'failed'.
  const [gradingState, setGradingState] = useState(null);
  const [submitError, setSubmitError] = useState(null);
  const [confirmUnanswered, setConfirmUnanswered] = useState(false);
  const [runResults, setRunResults] = useState({}); // item_id -> compiler output of the student's own trial run
  const [runningItemId, setRunningItemId] = useState(null);

  // AI Assistant Chat State for Post & Transfer Test phases
  const [chatMessages, setChatMessages] = useState([]);
  const [inputQuery, setInputQuery] = useState('');
  const [isAiLoading, setIsAiLoading] = useState(false);
  const [chatFilterMode, setChatFilterMode] = useState('dual'); // 'dual' | 'rag' | 'independent'
  const chatContainerRef = useRef(null);

  useEffect(() => {
    // Reset AI Assistant Chat when the exam phase changes. Deliberately NOT keyed on the current
    // question - navigating between questions must not wipe the conversation.
    setChatMessages([welcomeMessage(examType)]);
  }, [examType]);

  useEffect(() => {
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight;
    }
  }, [chatMessages, isAiLoading]);

  // The app shell's <main> is the scroll container (not the window), so bring the question card
  // back into view when moving between questions instead of leaving the user mid-page.
  const questionCardRef = useRef(null);
  const lastIndexRef = useRef(currentIndex);
  useEffect(() => {
    if (lastIndexRef.current === currentIndex) return;
    lastIndexRef.current = currentIndex;
    questionCardRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, [currentIndex]);

  const handleClearChat = () => {
    setChatMessages([welcomeMessage(examType, true)]);
  };

  const loadItems = useCallback(async (type) => {
    setIsSubmitted(false);
    setConfirmUnanswered(false);
    setScoreResult(null);
    setSubmitError(null);
    setSelectedAnswers({});
    setUserCodeAnswers({});
    setRunResults({});
    setCurrentIndex(0);
    try {
      const data = await apiService.getAssessmentItems(type);
      if (Array.isArray(data?.available)) setAvailableExams(data.available);
      const itemsList = data?.items || [];
      setAllItems(itemsList);
      // A paper is sat once. If this one is already in, show the recorded result rather
      // than a blank form the server would refuse anyway.
      if (data?.sitting?.status === 'completed' && data.sitting.submission_id) {
        const done = await apiService.getSubmission(data.sitting.submission_id);
        setGradingState(done.grading_status);
        setScoreResult({
          pct: done.score_pct ?? 0,
          correct: done.correct ?? 0,
          total: done.total ?? itemsList.length,
          results: done.results || [],
          submissionId: done.submission_id,
        });
        setIsSubmitted(true);
      }
    } catch (err) {
      // A locked paper comes back 403 with the list of papers that are open.
      if (Array.isArray(err.body?.available)) setAvailableExams(err.body.available);
      setAllItems([]);
      setSubmitError(err.message || 'Could not load this paper.');
    }
  }, []);

  // Declared after loadItems on purpose: the dependency array is evaluated during
  // render, so placing this above the useCallback threw "Cannot access 'loadItems'
  // before initialization" and took the whole assessment page down.
  useEffect(() => {
    loadItems(examType);
  }, [examType, loadItems]);

  // Derived, not stored: keeping a second copy of the list in state meant every loader
  // had to remember to re-filter it, and made loadItems depend on the selected chapter.
  const filteredItems = useMemo(() => {
    const chapter = CHAPTER_FILTERS[selectedChapter];
    if (!chapter) return allItems;
    return allItems.filter((item) => item.chapter?.includes(chapter));
  }, [allItems, selectedChapter]);

  const handleChapterFilter = (chap) => {
    setSelectedChapter(chap);
    setCurrentIndex(0);
  };

  const handleOptionSelect = (questionId, optionKey) => {
    setSelectedAnswers((prev) => ({
      ...prev,
      [questionId]: optionKey,
    }));
  };

  const handleSelectOption = (questionId, optionId) => {
    handleOptionSelect(questionId, optionId);
  };

  const handleCodeChange = (questionId, code) => {
    setUserCodeAnswers((prev) => ({
      ...prev,
      [questionId]: code,
    }));
  };

  // Trial run against the visible sample cases only - it never decides the grade, it just lets the
  // student see what the compiler makes of their code before they commit to submitting.
  const handleRunCode = async (item) => {
    const lang = item.type === 'html_coding' ? 'html' : 'c';
    const source = userCodeAnswers[item.id] !== undefined ? userCodeAnswers[item.id] : (item.code_snippet || '');
    setRunningItemId(item.id);
    setRunResults((prev) => ({ ...prev, [item.id]: null }));

    try {
      const res = await apiService.runCode(lang, source, item.sample_cases || [], 'run');
      setRunResults((prev) => ({
        ...prev,
        [item.id]: {
          status: res.status,
          compile_output: res.compile_output || '',
          testResults: res.test_results || [],
          passed_count: res.passed_count ?? 0,
        },
      }));
    } catch (err) {
      setRunResults((prev) => ({ ...prev, [item.id]: { status: 'ERROR', error: err.message, testResults: [] } }));
    } finally {
      setRunningItemId(null);
    }
  };

  // The server compiles and grades every item; the client only reports what comes back.
  // The server grades all items of the form, so progress is counted over allItems, never the
  // filtered view - otherwise a student who filters to one chapter is told they have finished
  // while the items they never saw are about to be marked wrong.
  const isAnswered = (item) => {
    if (item.type === 'concept_mcq') return Boolean(selectedAnswers[item.id]);
    const src = (userCodeAnswers[item.id] || '').trim();
    return Boolean(src) && src !== (item.code_snippet || '').trim();
  };
  const answeredCount = allItems.filter(isAnswered).length;
  const unansweredCount = allItems.length - answeredCount;

  const handleSubmitExam = async () => {
    // One deliberate confirmation when items are still blank: the chapter filter makes it easy
    // to reach the end of a chapter and assume the whole form is done.
    if (unansweredCount > 0 && !confirmUnanswered) {
      setConfirmUnanswered(true);
      return;
    }
    setIsSubmitting(true);
    setSubmitError(null);

    try {
      // The answers are saved the moment this returns; grading of the code items runs on
      // the server afterwards, so poll until the row settles instead of holding the
      // request open through five compiles.
      let res = await apiService.submitExam({
        exam_type: examType,
        chapter: selectedChapter,
        answers: selectedAnswers,
        code_answers: userCodeAnswers,
      });
      setIsSubmitted(true);
      setGradingState(res.grading_status);

      const started = Date.now();
      let delay = GRADING_POLL_MS;
      while (res.grading_status === 'pending' || res.grading_status === 'grading') {
        if (Date.now() - started > GRADING_WAIT_LIMIT_MS) {
          throw new Error('Your answers are saved, but marking is taking longer than expected. Please tell the invigilator; you do not need to resubmit.');
        }
        await new Promise((resolve) => setTimeout(resolve, delay));
        // Back off: sixty browsers polling every 1.5 s is 40 requests a second aimed at
        // the same server that is trying to mark their papers.
        delay = Math.min(Math.round(delay * 1.5), GRADING_POLL_MAX_MS);
        res = await apiService.getSubmission(res.submission_id);
        setGradingState(res.grading_status);
      }

      if (res.grading_status === 'failed') {
        throw new Error(`Your answers are saved, but marking failed (${res.error || 'unknown error'}). Please tell the invigilator; you do not need to resubmit.`);
      }

      setScoreResult({
        pct: res.score_pct ?? 0,
        correct: res.correct ?? 0,
        total: res.total ?? allItems.length,
        results: res.results || [],
        submissionId: res.submission_id,
      });

      apiService.logTelemetry('SUBMIT_ASSESSMENT', {
        exam_type: examType,
        chapter: selectedChapter,
        submission_id: res.submission_id,
        score: res.score_pct,
        correct: res.correct,
        total: res.total,
        timestamp: new Date().toISOString(),
      });
    } catch (err) {
      setSubmitError(err.message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSendAiMessage = async (queryText) => {
    const textToSend = queryText || inputQuery;
    if (!textToSend.trim()) return;

    const userMsg = {
      sender: 'user',
      text: textToSend,
      time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    setChatMessages((prev) => [...prev, userMsg]);
    if (!queryText) setInputQuery('');
    setIsAiLoading(true);

    const currentItem = filteredItems[currentIndex];
    const currentCode = userCodeAnswers[currentItem?.id] || currentItem?.code_snippet || '';

    try {
      const response = await apiService.queryTutor(
        textToSend,
        currentCode,
        currentItem?.id || 'prob_assessment',
        'REASONING_VISIBLE',
        {
          language,
          problem_title: currentItem?.title || '',
          problem_description: currentItem?.question || '',
        }
      );

      let replyText = '';
      if (response.answer) {
        replyText = response.answer;
      } else if (response.direct_answer) {
        replyText = response.direct_answer;
      } else if (response.reasoning_trace) {
        const rt = response.reasoning_trace;
        const promptLower = textToSend.toLowerCase();

        if (promptLower.includes('hint')) {
          replyText = `💡 **NCTB Pedagogical Hint for ${currentItem?.title || 'this question'}**:\n\n• **Core Concept**: ${rt.concept_applied || 'Loop & Control Logic'}\n\n• **Key Steps**:\n${(rt.problem_breakdown || []).slice(0, 3).join('\n')}\n\n• **Pro Tip**: ${rt.pedagogical_justification || 'Pay close attention to initial variable values and loop termination conditions.'}`;
        } else if (promptLower.includes('concept')) {
          replyText = `📖 **NCTB Concept Rule & Standard**:\n\n• **Applied Concept**: ${rt.concept_applied || 'Curriculum Control Structure'}\n\n• **Rule Explanation**: ${rt.pedagogical_justification || 'Follow standard NCTB HSC ICT guidelines.'}`;
        } else if (promptLower.includes('logic')) {
          replyText = `⚙️ **Step-by-Step Logic Breakdown**:\n\n${(rt.problem_breakdown || []).map((step) => `• ${step}`).join('\n')}`;
        } else {
          replyText = `💡 **NCTB Guidance for ${currentItem?.title || 'this question'}**:\n\n📌 **Concept**: ${rt.concept_applied || 'NCTB Programming Standard'}\n\n📝 **Logic Breakdown**:\n${(rt.problem_breakdown || []).map((step) => `• ${step}`).join('\n')}\n\n💡 **Rationale**: ${rt.pedagogical_justification || 'Follow standard variable initialization and loop conditions.'}`;

          if (rt.code_solution) {
            replyText += `\n\n💻 **Worked Solution Code**:\n\`\`\`c\n${rt.code_solution}\n\`\`\``;
          }
        }
      } else if (typeof response === 'string') {
        replyText = response;
      } else {
        replyText = `Here is the guidance for ${currentItem?.title || 'this question'}:\n\n• Focus on initializing variables properly.\n• Configure loop boundaries correctly (e.g. i <= N vs i < N).\n• Test with sample inputs.`;
      }

      if (response.grounded_passage?.passage || (typeof response.grounded_passage === 'string' && response.grounded_passage)) {
        const passageStr = typeof response.grounded_passage === 'string' ? response.grounded_passage : response.grounded_passage.passage;
        if (passageStr) {
          replyText += `\n\n📌 **NCTB Textbook Reference**:\n"${passageStr.substring(0, 220)}..."`;
        }
      }

      setChatMessages((prev) => [
        ...prev,
        {
          sender: 'ai',
          text: replyText,
          rag_answer: response.rag_answer,
          independent_ai_answer: response.independent_ai_answer || response.reasoning_trace,
          retrieved_passages: response.retrieved_passages || [],
          model: response.model,
          ai_status: response.ai_status,
          ai_error: response.error,
          time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        },
      ]);
    } catch (err) {
      setChatMessages((prev) => [
        ...prev,
        {
          sender: 'ai',
          text: `AI request failed: ${err.message}`,
          isError: true,
          time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        },
      ]);
    } finally {
      setIsAiLoading(false);
    }
  };

  const currentItem = filteredItems[currentIndex];
  const isAiAllowed = examType === 'post' || examType === 'transfer';

  // Rendered under the question card while an exam is in progress (so the pinned AI panel spans both),
  // and on its own once the exam is submitted or nothing is loaded.
  const questionIndex = (
      <div className="bg-surface-container p-6 rounded-2xl border border-outline-variant/30 space-y-4 shadow-xl">
        <div className="flex items-center justify-between border-b border-outline-variant/20 pb-3">
          <div className="flex items-center gap-2 text-xs font-bold text-on-surface">
            <BookOpen className="w-4 h-4 text-primary" />
            <span>NCTB RAG Curriculum Question Index (15 Items Total)</span>
          </div>
          <span className="px-2.5 py-0.5 rounded bg-primary/10 text-primary font-mono text-[10px] font-bold border border-primary/30">
            Chapters 4, 5 & 6
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs font-mono border-collapse">
            <thead>
              <tr className="border-b border-outline-variant/30 text-on-surface-variant text-[11px]">
                <th className="py-2.5 px-3">ID</th>
                <th className="py-2.5 px-3">Chapter</th>
                <th className="py-2.5 px-3">Item Title</th>
                <th className="py-2.5 px-3">Type</th>
                <th className="py-2.5 px-3">Curriculum Reference</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-outline-variant/10 text-on-surface">
              {allItems.map((item, idx) => (
                <tr key={item.id} className="hover:bg-surface-container-high/50 transition-colors">
                  <td className="py-3 px-3 font-bold text-primary">{idx + 1}</td>
                  <td className="py-3 px-3">{(item.chapter || '').split('—')[0]}</td>
                  <td className="py-3 px-3 font-sans font-medium">{item.title}</td>
                  <td className="py-3 px-3">
                    <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                      item.type === 'c_programming' ? 'bg-emerald-500/20 text-emerald-400' :
                      item.type === 'html_coding' ? 'bg-sky-500/20 text-sky-400' : 'bg-purple-500/20 text-purple-400'
                    }`}>
                      {item.type === 'c_programming' ? 'C Code' : item.type === 'html_coding' ? 'HTML Code' : 'MCQ'}
                    </span>
                  </td>
                  <td className="py-3 px-3 text-on-surface-variant">{item.curriculum_ref}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
  );

  return (
    <div className={`max-w-7xl mx-auto space-y-6 w-full ${!isSubmitted && currentItem ? 'pb-16 lg:pb-0' : 'pb-16'}`}>
      {/* Top Header & Assessment Module Selector Tabs */}
      <div className="bg-surface-container p-5 rounded-2xl border border-outline-variant/30 space-y-4 shadow-xl">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-11 h-11 rounded-xl bg-primary/20 text-primary flex items-center justify-center font-bold shadow-md border border-primary/30 shrink-0">
              <FileCheck className="w-6 h-6" />
            </div>
            <div>
              <h1 className="text-lg font-extrabold text-on-surface">NCTB HSC ICT Assessment & RAG Evaluation Suite</h1>
              <p className="text-xs text-on-surface-variant font-medium">15 Standard RAG Curriculum Questions (Chapters 4, 5 & 6)</p>
            </div>
          </div>

          {/* Papers open in protocol order. A participant can revisit forms they have sat
              and start the next one; the rest stay locked so the later papers are not read
              in advance. The server enforces the same rule - this only mirrors it. */}
          <div className="flex flex-wrap items-center gap-1 bg-surface-container-high p-1.5 rounded-xl border border-outline-variant/30 text-xs font-mono">
            {EXAM_TABS.map(({ type, label, activeClass }) => {
              const unlocked = availableExams.includes(type);
              const active = examType === type;
              return (
                <button
                  key={type}
                  onClick={() => unlocked && setExamType(type)}
                  disabled={!unlocked}
                  title={unlocked ? undefined : 'Complete the earlier papers to unlock this one.'}
                  className={`px-3.5 py-2 rounded-lg font-bold transition-all flex items-center gap-1.5 ${
                    active
                      ? `${activeClass} shadow-md`
                      : unlocked
                        ? 'text-on-surface-variant hover:text-on-surface'
                        : 'text-on-surface-variant/40 cursor-not-allowed'
                  }`}
                >
                  {!unlocked && <Lock className="w-3 h-3" />}
                  {label}
                </button>
              );
            })}
          </div>
        </div>

        {/* Chapter Filter Badges */}
        <div className="flex flex-wrap items-center gap-2 pt-3 border-t border-outline-variant/20 text-xs font-mono">
          <span className="text-on-surface-variant font-bold mr-1">Filter by Chapter:</span>
          <button
            onClick={() => handleChapterFilter('ALL')}
            className={`px-3 py-1.5 rounded-lg border transition-all font-bold ${
              selectedChapter === 'ALL'
                ? 'bg-primary text-on-primary border-primary shadow-sm'
                : 'bg-surface-container-high text-on-surface-variant hover:text-on-surface border-outline-variant/30'
            }`}
          >
            All 15 RAG Questions
          </button>

          <button
            onClick={() => handleChapterFilter('CHAP4')}
            className={`px-3 py-1.5 rounded-lg border transition-all font-bold flex items-center gap-1.5 ${
              selectedChapter === 'CHAP4'
                ? 'bg-sky-500 text-white border-sky-400 shadow-sm'
                : 'bg-surface-container-high text-on-surface-variant hover:text-on-surface border-outline-variant/30'
            }`}
          >
            <Globe className="w-3.5 h-3.5 text-sky-400" />
            Chapter 4: Web Design & HTML (8)
          </button>

          <button
            onClick={() => handleChapterFilter('CHAP5')}
            className={`px-3 py-1.5 rounded-lg border transition-all font-bold flex items-center gap-1.5 ${
              selectedChapter === 'CHAP5'
                ? 'bg-emerald-600 text-white border-emerald-500 shadow-sm'
                : 'bg-surface-container-high text-on-surface-variant hover:text-on-surface border-outline-variant/30'
            }`}
          >
            <Code className="w-3.5 h-3.5 text-emerald-400" />
            Chapter 5: C Programming (5)
          </button>

          <button
            onClick={() => handleChapterFilter('CHAP6')}
            className={`px-3 py-1.5 rounded-lg border transition-all font-bold flex items-center gap-1.5 ${
              selectedChapter === 'CHAP6'
                ? 'bg-purple-600 text-white border-purple-500 shadow-sm'
                : 'bg-surface-container-high text-on-surface-variant hover:text-on-surface border-outline-variant/30'
            }`}
          >
            <Database className="w-3.5 h-3.5 text-purple-400" />
            Chapter 6: DBMS (2)
          </button>

          <span className="ml-auto font-bold text-on-surface-variant">
            উত্তর দেওয়া হয়েছে (Answered): <span className="text-primary">{answeredCount}</span> / {allItems.length}
          </span>
        </div>

        {selectedChapter !== 'ALL' && !isSubmitted && (
          <div className="mt-3 flex items-start gap-2 rounded-xl border border-warning/30 bg-warning/10 p-3 text-xs text-warning">
            <ShieldAlert className="w-4 h-4 shrink-0 mt-0.5" />
            <span>
              ফিল্টার শুধু দেখার জন্য — জমা দিলে পুরো {allItems.length}টি প্রশ্নই মূল্যায়ন হবে, না দেখা প্রশ্নগুলো ভুল ধরা হবে।
              <span className="opacity-80"> (The filter only changes the view. All {allItems.length} items are graded; anything left unanswered counts as wrong.)</span>
            </span>
          </div>
        )}
      </div>

      {/* Phase Banner Notification */}
      {examType === 'pre' && (
        <div className="bg-primary/10 border border-primary/30 p-4 rounded-xl flex items-center gap-3 text-xs text-primary font-medium shadow-sm">
          <ShieldAlert className="w-5 h-5 shrink-0" />
          <span>
            <strong>Pre-Test Baseline Assessment:</strong> AI Assistance is disabled during Pre-Test so we can measure your initial coding knowledge before using TRACE Tutor.
          </span>
        </div>
      )}

      {isAiAllowed && (
        <div className="bg-emerald-500/10 border border-emerald-500/30 p-4 rounded-xl flex items-center justify-between gap-3 text-xs text-emerald-400 font-medium shadow-sm">
          <div className="flex items-center gap-3">
            <Sparkles className="w-5 h-5 shrink-0 text-emerald-400 animate-pulse" />
            <span>
              <strong>AI Tutor Assistant Enabled ({examType === 'post' ? 'Post-Test' : 'Transfer Test'}):</strong> You can chat with TRACE AI Assistant on the right panel to ask for explanations, hints, or logic steps like ChatGPT!
            </span>
          </div>
          <span className="px-2.5 py-1 rounded bg-emerald-500/20 text-emerald-300 font-mono font-bold text-[11px] border border-emerald-500/40 shrink-0">
            AI TUTOR ACTIVE
          </span>
        </div>
      )}

      {examType === 'withdrawal' && (
        <div className="bg-amber-500/10 border border-amber-500/30 p-4 rounded-xl flex items-center justify-between gap-3 text-xs text-amber-300 font-medium shadow-sm">
          <div className="flex items-center gap-3">
            <Lock className="w-5 h-5 shrink-0 text-amber-400" />
            <span>
              <strong>AI Tutor Withdrawal Task:</strong> AI assistance is disabled here to measure independent skill retention without AI reliance.
            </span>
          </div>
          <span className="px-2.5 py-1 rounded bg-amber-500/20 text-amber-300 font-mono font-bold text-[11px] border border-amber-500/40 shrink-0">
            NO AI HELP
          </span>
        </div>
      )}

      {/* Main Grid: Question Content + AI Assistant (Side-by-Side when AI is enabled) */}
      {!isSubmitted && currentItem && (
        <div className={`grid grid-cols-1 ${isAiAllowed ? 'lg:grid-cols-12' : ''} gap-6 items-start`}>
          {/* Main Question Card (7 cols when AI enabled, full width when disabled). It scrolls with the page. */}
          <div ref={questionCardRef} data-testid="question-card" className={`${isAiAllowed ? 'lg:col-span-7' : ''} scroll-mt-4 bg-surface-container p-6 sm:p-8 rounded-2xl border border-outline-variant/30 space-y-6 shadow-2xl`}>
            {/* Question Header & Metadata */}
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-on-surface-variant border-b border-outline-variant/20 pb-3">
              <span className="font-mono font-extrabold text-primary text-sm">
                Question {currentIndex + 1} of {filteredItems.length}
              </span>
              <div className="flex items-center gap-2">
                <span className="px-2.5 py-1 rounded-md bg-primary/10 text-primary font-mono font-bold border border-primary/30">
                  {currentItem.chapter}
                </span>
                <span className="font-mono text-emerald-400 font-bold bg-emerald-500/10 px-2 py-1 rounded border border-emerald-500/30">
                  {currentItem.curriculum_ref}
                </span>
              </div>
            </div>

            <div>
              <h2 className="text-xs font-mono font-bold text-primary uppercase tracking-wider mb-1.5">
                {currentItem.title}
              </h2>
              <h3 className="text-base font-bold text-on-surface leading-relaxed">{currentItem.question}</h3>
            </div>

            {/* Starter Code Snippet Template (UNSOLVED) */}
            {currentItem.code_snippet && (
              <div className="space-y-1.5">
                <span className="text-[11px] font-mono font-bold text-on-surface-variant uppercase flex items-center gap-1.5">
                  <Terminal className="w-3.5 h-3.5 text-primary" /> STARTER CODE TEMPLATE (STUDENT TO COMPLETE):
                </span>
                <div className="bg-surface-container-lowest p-4 rounded-xl border border-outline-variant/30 overflow-x-auto shadow-inner">
                  <pre className="font-mono text-xs text-primary leading-relaxed whitespace-pre-wrap">
                    {currentItem.code_snippet}
                  </pre>
                </div>
              </div>
            )}

            {/* I/O contract - the server grader matches output literally, so the student must see it before answering */}
            {(currentItem.type === 'c_programming' || currentItem.type === 'html_coding') &&
              (currentItem.input_format || currentItem.output_format || currentItem.sample_cases?.length > 0) && (
              <div className="bg-surface-container-lowest p-4 rounded-xl border border-outline-variant/30 space-y-3.5 shadow-inner">
                <span className="text-[11px] font-mono font-bold text-on-surface-variant uppercase flex items-center gap-1.5">
                  <ArrowRightLeft className="w-3.5 h-3.5 text-primary" /> ইনপুট / আউটপুট চুক্তি (Input / Output contract)
                </span>

                {currentItem.input_format && (
                  <div>
                    <span className="text-[11px] font-mono font-bold text-primary uppercase tracking-wider block">ইনপুট ফরম্যাট (Input format)</span>
                    <p className="text-xs text-on-surface-variant font-mono leading-relaxed">{currentItem.input_format}</p>
                  </div>
                )}

                {currentItem.output_format && (
                  <div>
                    <span className="text-[11px] font-mono font-bold text-primary uppercase tracking-wider block">আউটপুট ফরম্যাট (Output format)</span>
                    <p className="text-xs text-on-surface-variant font-mono leading-relaxed">{currentItem.output_format}</p>
                  </div>
                )}

                {currentItem.sample_cases?.length > 0 && (
                  <div className="space-y-2">
                    <span className="text-[11px] font-mono font-bold text-on-surface uppercase tracking-wider block">নমুনা কেস (Sample cases)</span>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                      {currentItem.sample_cases.map((sc, idx) => (
                        <div key={idx} className="bg-surface-container-high p-3 rounded-xl border border-outline-variant/30 text-xs font-mono space-y-1">
                          <div className="flex justify-between gap-2 text-on-surface-variant">
                            <span>Input:</span> <span className="text-primary font-bold whitespace-pre-wrap text-right">{(sc.input || '').trim() || '(none)'}</span>
                          </div>
                          <div className="flex justify-between gap-2 text-on-surface-variant">
                            <span>Output:</span> <span className="text-emerald-400 font-bold whitespace-pre-wrap text-right">{sc.output}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <p className="text-[11px] text-amber-500 bg-amber-500/10 border border-amber-500/30 rounded-lg p-2 leading-relaxed">
                  আউটপুট হুবহু মিলতে হবে — বাড়তি লেখা বা ভিন্ন বানান ভুল হিসেবে গণ্য হবে। (The grader compares your output exactly.)
                </p>
              </div>
            )}

            {/* Interactive Workspace Code Editor for Coding Tasks */}
            {(currentItem.type === 'c_programming' || currentItem.type === 'html_coding') ? (
              <div className="space-y-2">
                {/* A row, not a <label>: the Run button is itself labelable, so wrapping
                    both in one label attached the caption to the button instead of to
                    the code box. The caption now points at the textarea explicitly. */}
                <div className="text-xs font-mono font-bold text-on-surface flex flex-wrap items-center justify-between gap-2">
                  <label htmlFor={`code-answer-${currentItem.id}`} className="flex items-center gap-1.5">
                    <Code className="w-4 h-4 text-primary" /> Write Your Code Solution ({currentItem.type === 'html_coding' ? 'HTML Markup' : 'C Language'}):
                  </label>
                  <Button
                    variant="surface"
                    size="sm"
                    onClick={() => handleRunCode(currentItem)}
                    disabled={runningItemId === currentItem.id}
                    title="জমা দেওয়ার আগে নিজের কোড পরীক্ষা করুন (Test your code before submitting)"
                  >
                    {runningItemId === currentItem.id
                      ? <><Loader2 className="w-3.5 h-3.5 animate-spin" /> চলছে... (Running)</>
                      : <><Play className="w-3.5 h-3.5 text-primary" /> রান করুন (Run)</>}
                  </Button>
                </div>
                <textarea
                  id={`code-answer-${currentItem.id}`}
                  rows={8}
                  value={userCodeAnswers[currentItem.id] !== undefined ? userCodeAnswers[currentItem.id] : currentItem.code_snippet}
                  onChange={(e) => handleCodeChange(currentItem.id, e.target.value)}
                  placeholder="Write your complete code solution here..."
                  className="w-full bg-surface-container-lowest text-on-surface p-4 rounded-xl font-mono text-xs border border-outline-variant/40 focus:border-primary outline-none transition-all shadow-inner leading-relaxed"
                />

                {runResults[currentItem.id] && (
                  <div className="bg-surface-container-lowest p-3.5 rounded-xl border border-outline-variant/30 space-y-2 text-xs shadow-inner">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="text-[11px] font-mono font-bold text-on-surface-variant uppercase flex items-center gap-1.5">
                        <Terminal className="w-3.5 h-3.5 text-primary" /> ট্রায়াল রানের ফল (Trial run result)
                      </span>
                      {runResults[currentItem.id].testResults.length > 0 && (
                        <Badge tone={runResults[currentItem.id].passed_count === runResults[currentItem.id].testResults.length ? 'success' : 'warning'}>
                          {runResults[currentItem.id].passed_count}/{runResults[currentItem.id].testResults.length} পাস (passed)
                        </Badge>
                      )}
                    </div>

                    {runResults[currentItem.id].status === 'ERROR' && (
                      <p className="text-rose-400 font-mono flex items-start gap-1.5">
                        <AlertCircle className="w-3.5 h-3.5 shrink-0 mt-0.5" /> {runResults[currentItem.id].error}
                      </p>
                    )}

                    {runResults[currentItem.id].status === 'COMPILE_ERROR' && (
                      <p className="text-rose-400 font-bold flex items-start gap-1.5">
                        <AlertCircle className="w-3.5 h-3.5 shrink-0 mt-0.5" /> কম্পাইল ব্যর্থ হয়েছে (Compilation failed)
                      </p>
                    )}

                    {runResults[currentItem.id].compile_output && (
                      <pre className="bg-surface-container p-2.5 rounded-lg border border-outline-variant/20 font-mono text-[10px] text-on-surface-variant whitespace-pre-wrap max-h-40 overflow-y-auto">
                        {runResults[currentItem.id].compile_output}
                      </pre>
                    )}

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                      {runResults[currentItem.id].testResults.map((tr, idx) => (
                        <div
                          key={tr.id ?? idx}
                          className={`bg-surface-container p-2.5 rounded-xl border space-y-1 ${tr.passed ? 'border-emerald-500/30' : 'border-rose-500/40 bg-rose-500/5'}`}
                        >
                          <div className="flex items-center justify-between gap-2">
                            <span className="font-bold text-on-surface truncate">
                              {tr.name || `নমুনা ${idx + 1} (Sample ${idx + 1})`}
                            </span>
                            <span className={`px-2 py-0.5 rounded font-extrabold text-[10px] shrink-0 border ${tr.passed ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30' : 'bg-rose-500/20 text-rose-400 border-rose-500/40'}`}>
                              {tr.passed ? 'PASSED' : tr.timed_out ? 'TIMEOUT' : 'FAILED'}
                            </span>
                          </div>
                          {tr.expected !== undefined && (
                            <div className="text-[10px] text-on-surface-variant font-mono">Expected: <strong className="text-emerald-400">{tr.expected || '(any)'}</strong></div>
                          )}
                          <div className="text-[10px] text-on-surface-variant font-mono">Actual: <strong className={tr.passed ? 'text-on-surface' : 'text-rose-400'}>{tr.actual || '(no output)'}</strong></div>
                          {tr.stderr && <pre className="text-[10px] text-rose-400 whitespace-pre-wrap">{tr.stderr}</pre>}
                        </div>
                      ))}
                    </div>

                    <p className="text-[10px] text-on-surface-variant font-mono">
                      এটি শুধু অনুশীলন রান; চূড়ান্ত নম্বর সার্ভার দেবে। (Trial run only - the server decides the final score.)
                    </p>
                  </div>
                )}
              </div>
            ) : (
              /* MCQ Options */
              <div className="space-y-3">
                {currentItem.options?.map((opt) => {
                  const isSelected = selectedAnswers[currentItem.id] === opt.id;
                  return (
                    <button
                      key={opt.id}
                      onClick={() => handleSelectOption(currentItem.id, opt.id)}
                      className={`w-full p-4 rounded-xl border text-left text-xs transition-all flex items-center justify-between ${
                        isSelected
                          ? 'bg-primary/20 border-primary text-on-surface font-semibold shadow-md shadow-primary/10'
                          : 'bg-surface-container-high border-outline-variant/30 text-on-surface-variant hover:text-on-surface hover:border-outline'
                      }`}
                    >
                      <span className="flex items-center gap-3">
                        <span className={`w-7 h-7 rounded-lg font-mono font-bold text-xs flex items-center justify-center ${isSelected ? 'bg-primary text-on-primary' : 'bg-surface-container text-on-surface-variant'}`}>
                          {opt.id.toUpperCase()}
                        </span>
                        {opt.text}
                      </span>
                      {isSelected && <CheckCircle2 className="w-4 h-4 text-primary" />}
                    </button>
                  );
                })}
              </div>
            )}

            {confirmUnanswered && !isSubmitting && (
              <div className="mb-3 flex items-start gap-2 rounded-xl border border-warning/30 bg-warning/10 p-3 text-xs text-warning">
                <ShieldAlert className="w-4 h-4 shrink-0 mt-0.5" />
                <span>
                  <strong>{unansweredCount}টি প্রশ্নের উত্তর দেওয়া হয়নি</strong> — এগুলো ভুল হিসেবে গণ্য হবে।
                  আবার Submit চাপলে এভাবেই জমা হয়ে যাবে।
                  <span className="opacity-80"> ({unansweredCount} unanswered; they will be marked wrong. Press Submit again to send it as is.)</span>
                </span>
              </div>
            )}

            {submitError && (
              <div className="bg-rose-500/10 border border-rose-500/30 text-rose-400 rounded-xl p-3 text-xs font-medium flex items-start gap-2">
                <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                <span>
                  <strong>জমা দেওয়া যায়নি (Submission failed):</strong> {submitError}
                </span>
              </div>
            )}

            {/* Navigation Controls */}
            <div className="flex items-center justify-between pt-4 border-t border-outline-variant/20">
              <button
                onClick={() => setCurrentIndex((prev) => Math.max(0, prev - 1))}
                disabled={currentIndex === 0}
                className="px-4 py-2.5 rounded-xl bg-surface-container-high text-xs text-on-surface-variant hover:text-on-surface disabled:opacity-40 font-bold border border-outline-variant/30"
              >
                Previous Question
              </button>

              <div className="flex items-center gap-2">
                {currentIndex < filteredItems.length - 1 && (
                  <button
                    onClick={() => setCurrentIndex((prev) => Math.min(filteredItems.length - 1, prev + 1))}
                    className="px-6 py-2.5 rounded-xl bg-primary text-on-primary font-bold text-xs shadow-md shadow-primary/20 flex items-center gap-1.5 hover:bg-primary-container transition-all"
                  >
                    Next Question <ArrowRight className="w-4 h-4" />
                  </button>
                )}
                <button
                  onClick={handleSubmitExam}
                  disabled={isSubmitting}
                  className="px-6 py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-600 disabled:opacity-50 disabled:pointer-events-none text-on-surface font-bold text-xs shadow-lg shadow-emerald-500/20 flex items-center gap-1.5 transition-all"
                >
                  {isSubmitting
                    ? (gradingState === 'pending' || gradingState === 'grading'
                      ? <>উত্তর সংরক্ষিত — মার্কিং চলছে (Saved — marking…) <Loader2 className="w-4 h-4 animate-spin" /></>
                      : <>জমা হচ্ছে... (Submitting) <Loader2 className="w-4 h-4 animate-spin" /></>)
                    : confirmUnanswered
                      ? <>{unansweredCount}টি বাদ রেখে জমা দিন (Submit anyway) <CheckCircle2 className="w-4 h-4" /></>
                      : <>Submit Assessment <CheckCircle2 className="w-4 h-4" /></>}
                </button>
              </div>
            </div>
          </div>

          {/* AI Assistant Interactive Panel (Rendered Side-by-Side in Post & Transfer Test phases) */}
          {isAiAllowed && (
            <div
              data-testid="ai-panel"
              className="lg:col-span-5 lg:row-span-2 lg:sticky lg:top-0 h-[70vh] min-h-[460px] lg:h-[calc(100vh-6.5rem)] bg-surface-container rounded-2xl border border-outline-variant/30 flex flex-col shadow-2xl overflow-hidden"
            >
              {/* AI Chat Drawer Header */}
              <div className="p-3.5 bg-surface-container-high border-b border-outline-variant/30 space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2.5">
                    <div className="w-8 h-8 rounded-lg bg-emerald-500/20 text-emerald-400 flex items-center justify-center font-bold shadow-inner">
                      <Bot className="w-5 h-5" />
                    </div>
                    <div>
                      <h3 className="text-xs font-bold text-on-surface">TRACE Tutor AI Assistant</h3>
                      <span className="text-[10px] font-mono text-emerald-400 flex items-center gap-1">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" /> Active in {examType === 'post' ? 'Post-Test' : 'Transfer Test'}
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={handleClearChat}
                      title="Clear chat messages"
                      className="px-2.5 py-1 rounded-lg bg-surface-container hover:bg-rose-500/20 text-rose-400 font-mono text-[10px] font-bold border border-rose-500/30 flex items-center gap-1 transition-all shadow-sm"
                    >
                      <Trash2 className="w-3 h-3 text-rose-400" />
                      <span>Clear Chat</span>
                    </button>
                    <span className="px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 font-mono text-[10px] font-bold border border-emerald-500/30">
                      Dual RAG + AI
                    </span>
                  </div>
                </div>

                {/* Structured View Mode Selector */}
                <div className="flex items-center gap-1 bg-surface-container-lowest p-1 rounded-xl border border-outline-variant/20 text-[11px] font-mono">
                  <button
                    onClick={() => setChatFilterMode('dual')}
                    className={`flex-1 py-1 px-2 rounded-lg font-bold transition-all ${
                      chatFilterMode === 'dual'
                        ? 'bg-primary text-on-primary shadow-sm'
                        : 'text-on-surface-variant hover:text-on-surface'
                    }`}
                  >
                    ✨ Dual View
                  </button>
                  <button
                    onClick={() => setChatFilterMode('rag')}
                    className={`flex-1 py-1 px-2 rounded-lg font-bold transition-all ${
                      chatFilterMode === 'rag'
                        ? 'bg-sky-500 text-on-surface shadow-sm'
                        : 'text-on-surface-variant hover:text-on-surface'
                    }`}
                  >
                    📖 RAG Book
                  </button>
                  <button
                    onClick={() => setChatFilterMode('independent')}
                    className={`flex-1 py-1 px-2 rounded-lg font-bold transition-all ${
                      chatFilterMode === 'independent'
                        ? 'bg-purple-500 text-on-surface shadow-sm'
                        : 'text-on-surface-variant hover:text-on-surface'
                    }`}
                  >
                    🤖 Independent AI
                  </button>
                </div>
              </div>

              {/* Suggested Quick Prompts */}
              <div className="p-2.5 bg-surface-container-lowest border-b border-outline-variant/20 flex items-center gap-1.5 overflow-x-auto text-[11px] font-mono">
                <button
                  onClick={() => handleSendAiMessage('Give me a hint for this question without spoiling the full answer')}
                  className="px-2.5 py-1 rounded-lg bg-surface-container-high hover:bg-surface-container-highest text-primary whitespace-nowrap border border-primary/20 flex items-center gap-1"
                >
                  <Lightbulb className="w-3 h-3" /> Hint
                </button>
                <button
                  onClick={() => handleSendAiMessage('Explain the core concept and NCTB textbook rule for this problem')}
                  className="px-2.5 py-1 rounded-lg bg-surface-container-high hover:bg-surface-container-highest text-sky-400 whitespace-nowrap border border-sky-500/20 flex items-center gap-1"
                >
                  <BookOpen className="w-3 h-3" /> Concept Rule
                </button>
                <button
                  onClick={() => handleSendAiMessage('How should I structure the main logic and loop condition?')}
                  className="px-2.5 py-1 rounded-lg bg-surface-container-high hover:bg-surface-container-highest text-purple-400 whitespace-nowrap border border-purple-500/20 flex items-center gap-1"
                >
                  <Code className="w-3 h-3" /> Logic Structure
                </button>
              </div>

              {/* Chat History Body */}
              <div ref={chatContainerRef} className="flex-1 overflow-y-auto overscroll-contain p-4 space-y-3.5 text-xs">
                {chatMessages.map((msg, idx) => (
                  <div
                    key={idx}
                    className={`flex items-start gap-2.5 ${msg.sender === 'user' ? 'flex-row-reverse' : ''}`}
                  >
                    <div className={`w-7 h-7 rounded-lg flex items-center justify-center shrink-0 ${
                      msg.sender === 'user' ? 'bg-primary text-on-primary' : 'bg-emerald-500/20 text-emerald-400'
                    }`}>
                      {msg.sender === 'user' ? <User className="w-4 h-4" /> : <Bot className="w-4 h-4" />}
                    </div>

                    <div className={`max-w-[88%] space-y-2 ${
                      msg.sender === 'user'
                        ? 'bg-primary text-on-primary p-3 rounded-2xl rounded-tr-none'
                        : 'bg-surface-container-lowest text-on-surface border border-outline-variant/20 p-3.5 rounded-2xl rounded-tl-none space-y-3'
                    }`}>
                      {msg.sender === 'user' ? (
                        <p className="leading-relaxed whitespace-pre-wrap">{msg.text}</p>
                      ) : (
                        <div className="space-y-3">
                          {/* SECTION A: RAG NCTB TEXTBOOK GROUNDED ANSWER */}
                          {(chatFilterMode === 'dual' || chatFilterMode === 'rag') && msg.rag_answer && (
                            <div className="bg-sky-500/10 border border-sky-500/30 rounded-xl p-3 space-y-1.5">
                              <div className="flex items-center justify-between">
                                <span className="text-[11px] font-extrabold text-sky-400 font-mono flex items-center gap-1">
                                  <BookOpen className="w-3.5 h-3.5" /> 📖 NCTB Textbook RAG Answer
                                </span>
                                <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-sky-500/20 text-sky-300 font-bold">
                                  Grounded
                                </span>
                              </div>
                              <h5 className="font-bold text-on-surface text-xs">{msg.rag_answer.textbook_rule}</h5>
                              <p className="text-[10px] text-on-surface-variant font-mono">📍 {msg.rag_answer.curriculum_citation}</p>
                              <p className="text-[11px] italic bg-surface-container p-2.5 rounded-lg border border-outline-variant/20 leading-relaxed text-on-surface whitespace-pre-wrap">
                                &ldquo;{msg.rag_answer.textbook_explanation}&rdquo;
                              </p>
                              {msg.retrieved_passages?.length > 0 && (
                                <details className="text-[10px] text-on-surface-variant">
                                  <summary className="cursor-pointer font-mono font-bold text-sky-400">Retrieved passages ({msg.retrieved_passages.length})</summary>
                                  <div className="mt-1 space-y-1">
                                    {msg.retrieved_passages.map((p, i) => (
                                      <div key={p.id || i} className="bg-surface-container p-2 rounded-lg border border-outline-variant/20">
                                        <span className="font-mono font-bold text-on-surface">[{i + 1}] {p.source_ref}</span>
                                        <span className="ml-1 text-sky-400">{Math.round((p.similarity_score || 0) * 100)}%</span>
                                        <p className="line-clamp-3 whitespace-pre-wrap mt-0.5">{p.passage}</p>
                                      </div>
                                    ))}
                                  </div>
                                </details>
                              )}
                            </div>
                          )}

                          {msg.ai_status === 'fallback' && (
                            <p className="text-[10px] text-amber-500 bg-amber-500/10 border border-amber-500/30 rounded-lg p-2">
                              {msg.model} did not respond: {msg.ai_error}
                            </p>
                          )}

                          {/* SECTION B: INDEPENDENT AI REASONING & CODE */}
                          {(chatFilterMode === 'dual' || chatFilterMode === 'independent') && msg.independent_ai_answer && (
                            <div className="bg-purple-500/10 border border-purple-500/30 rounded-xl p-3 space-y-2">
                              <div className="flex items-center justify-between">
                                <span className="text-[11px] font-extrabold text-purple-400 font-mono flex items-center gap-1">
                                  <Sparkles className="w-3.5 h-3.5" /> 🤖 Independent AI Explanation
                                </span>
                                <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-purple-500/20 text-purple-300 font-bold">
                                  {msg.model || 'Gemini'}
                                </span>
                              </div>

                              {msg.independent_ai_answer.concept_applied && (
                                <p className="text-xs font-bold text-on-surface">
                                  💡 Concept: <span className="text-purple-300 font-semibold">{msg.independent_ai_answer.concept_applied}</span>
                                </p>
                              )}

                              {msg.independent_ai_answer.problem_breakdown && (
                                <div className="space-y-1">
                                  <span className="text-[10px] font-mono uppercase text-purple-400 font-bold block">Logic Breakdown:</span>
                                  {msg.independent_ai_answer.problem_breakdown.map((st, i) => (
                                    <p key={i} className="text-xs text-on-surface leading-snug">• {st}</p>
                                  ))}
                                </div>
                              )}

                              {msg.independent_ai_answer.pedagogical_justification && (
                                <p className="text-[11px] text-on-surface font-medium bg-surface-container p-2 rounded-lg leading-relaxed">
                                  🧠 {msg.independent_ai_answer.pedagogical_justification}
                                </p>
                              )}

                              {msg.independent_ai_answer.code_solution && (
                                <div className="bg-slate-900 p-2.5 rounded-lg font-mono text-[11px] text-cyan-300 overflow-x-auto">
                                  <pre>{msg.independent_ai_answer.code_solution}</pre>
                                </div>
                              )}
                            </div>
                          )}

                          {/* Fallback formatted message text */}
                          {!msg.rag_answer && !msg.independent_ai_answer && (
                            <p className={`leading-relaxed whitespace-pre-wrap ${msg.isError ? 'text-rose-400 font-mono' : ''}`}>{msg.text}</p>
                          )}
                        </div>
                      )}

                      <span className={`text-[9px] font-mono block text-right ${msg.sender === 'user' ? 'text-on-primary/70' : 'text-on-surface-variant'}`}>
                        {msg.time}
                      </span>
                    </div>
                  </div>
                ))}

                {isAiLoading && (
                  <div className="flex items-center gap-2 text-xs text-primary font-mono animate-pulse p-2">
                    <Bot className="w-4 h-4 text-primary" />
                    <span>TRACE AI is retrieving RAG passages & generating AI concept response...</span>
                  </div>
                )}
              </div>

              {/* Input Footer */}
              <div className="p-3 bg-surface-container-high border-t border-outline-variant/30 flex items-center gap-2">
                <input
                  type="text"
                  value={inputQuery}
                  onChange={(e) => setInputQuery(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleSendAiMessage()}
                  placeholder="Ask AI Assistant for help, hints or logic..."
                  aria-label="Ask the AI assistant for help, hints or logic"
                  className="flex-1 bg-surface-container-lowest text-on-surface text-xs rounded-xl px-3.5 py-2.5 border border-outline-variant/30 outline-none focus:border-primary"
                />
                <button
                  onClick={() => handleSendAiMessage()}
                  disabled={isAiLoading || !inputQuery.trim()}
                  className="p-2.5 rounded-xl bg-primary text-on-primary hover:bg-primary-container disabled:opacity-40 transition-all shrink-0"
                >
                  <Send className="w-4 h-4" />
                </button>
              </div>
            </div>
          )}

          {/* Question index sits under the question card, so the pinned AI panel (row-span-2) stays put across both. */}
          <div className={`${isAiAllowed ? 'lg:col-span-7' : ''} lg:pb-16`}>{questionIndex}</div>
        </div>
      )}

      {/* Exam Result Screen - every number here comes from the server grader */}
      {isSubmitted && scoreResult && (
        <div className="space-y-6 max-w-3xl mx-auto">
          <div className="bg-surface-container p-8 sm:p-12 rounded-2xl border border-outline-variant/30 text-center space-y-6 shadow-2xl">
            <div className="w-20 h-20 rounded-full bg-emerald-500/20 text-emerald-400 flex items-center justify-center mx-auto shadow-inner">
              <Award className="w-12 h-12" />
            </div>

            <h2 className="text-3xl font-extrabold text-on-surface">Assessment Complete!</h2>
            <div className="text-5xl font-black text-primary font-mono">{scoreResult.pct}%</div>
            <p className="text-xs text-on-surface-variant leading-relaxed">
              You completed {scoreResult.correct} out of {scoreResult.total} items correctly in this {examType.toUpperCase()} assessment session.
            </p>

            <button
              onClick={() => loadItems(examType)}
              className="px-6 py-3 rounded-xl bg-surface-container-high hover:bg-surface-container-highest text-on-surface font-bold text-xs inline-flex items-center gap-2 border border-outline-variant/30 shadow-md"
            >
              <RefreshCw className="w-4 h-4" /> Retake Assessment
            </button>
          </div>

          {scoreResult.results?.length > 0 && (
            <div className="bg-surface-container p-6 rounded-2xl border border-outline-variant/30 space-y-3 shadow-xl">
              <div className="flex items-center justify-between border-b border-outline-variant/20 pb-3">
                <span className="text-xs font-bold text-on-surface flex items-center gap-2">
                  <FileCheck className="w-4 h-4 text-primary" /> প্রতিটি প্রশ্নের ফলাফল (Per-question results)
                </span>
                <Badge tone="neutral">সার্ভার গ্রেডেড (Server graded)</Badge>
              </div>

              {scoreResult.results.map((res, idx) => (
                <div
                  key={res.item_id || idx}
                  className={`p-3.5 rounded-xl border space-y-1.5 ${res.correct ? 'bg-emerald-500/5 border-emerald-500/30' : 'bg-rose-500/5 border-rose-500/40'}`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <span className="text-xs font-bold text-on-surface leading-snug">
                      <span className="font-mono text-on-surface-variant mr-1.5">{idx + 1}.</span>{res.title}
                    </span>
                    <span className={`px-2 py-0.5 rounded font-extrabold text-[10px] shrink-0 border flex items-center gap-1 ${res.correct ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30' : 'bg-rose-500/20 text-rose-400 border-rose-500/40'}`}>
                      {res.correct ? <CheckCircle2 className="w-3 h-3" /> : <XCircle className="w-3 h-3" />}
                      {res.correct ? 'সঠিক (Correct)' : 'ভুল (Incorrect)'}
                    </span>
                  </div>

                  {typeof res.total_tests === 'number' && res.total_tests > 0 && (
                    <div className="text-[11px] font-mono text-on-surface-variant">
                      {res.passed_count ?? 0}/{res.total_tests} {res.type === 'html_coding' ? 'শর্ত পাস (checks passed)' : 'টেস্ট কেস পাস (test cases passed)'}
                    </div>
                  )}

                  {res.detail && <p className="text-[11px] text-on-surface-variant leading-relaxed">{res.detail}</p>}

                  {res.compile_output && (
                    <details className="text-[10px] text-on-surface-variant">
                      <summary className="cursor-pointer font-mono font-bold text-rose-400">কম্পাইলার আউটপুট (Compiler output)</summary>
                      <pre className="mt-1 bg-surface-container-lowest p-2.5 rounded-lg border border-outline-variant/20 font-mono whitespace-pre-wrap max-h-48 overflow-y-auto">
                        {res.compile_output}
                      </pre>
                    </details>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {(isSubmitted || !currentItem) && questionIndex}
    </div>
  );
};
