import React, { useState, useEffect, useRef } from 'react';
import { apiService } from '../services/api';
import { useAuth } from '../context/AuthContext';
import {
  FileCheck,
  CheckCircle2,
  Clock,
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
  MessageSquare,
  HelpCircle,
  Lightbulb,
  Lock,
  User,
  ChevronRight,
  Terminal,
  Zap,
  Trash2,
  RotateCcw
} from 'lucide-react';

export const AssessmentPage = () => {
  const { language } = useAuth();
  const [examType, setExamType] = useState('pre'); // 'pre', 'post', 'transfer', 'withdrawal'
  const [selectedChapter, setSelectedChapter] = useState('ALL'); // 'ALL', 'CHAP4', 'CHAP5', 'CHAP6'
  const [allItems, setAllItems] = useState([]);
  const [filteredItems, setFilteredItems] = useState([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [selectedAnswers, setSelectedAnswers] = useState({});
  const [userCodeAnswers, setUserCodeAnswers] = useState({});
  const [isSubmitted, setIsSubmitted] = useState(false);
  const [scoreResult, setScoreResult] = useState(null);

  // AI Assistant Chat State for Post & Transfer Test phases
  const [chatMessages, setChatMessages] = useState([]);
  const [inputQuery, setInputQuery] = useState('');
  const [isAiLoading, setIsAiLoading] = useState(false);
  const [chatFilterMode, setChatFilterMode] = useState('dual'); // 'dual' | 'rag' | 'independent'
  const chatContainerRef = useRef(null);

  useEffect(() => {
    loadItems(examType);
  }, [examType]);

  useEffect(() => {
    // Reset AI Assistant Chat when exam type or current question changes
    setChatMessages([
      {
        sender: 'ai',
        text: `👋 Hello! I am your TRACE Tutor AI Assistant (NCTB ICT Specialist). You are in the ${
          examType === 'post' ? 'Post-Test' : examType === 'transfer' ? 'Transfer Test' : 'Assessment'
        } phase where AI assistance is fully active. I provide dual-mode guidance: both NCTB Textbook RAG answers and Independent AI logic explanations!`,
        rag_answer: {
          textbook_rule: 'NCTB HSC ICT Chapter 5 Standard C Programming Syntax & Control Logic',
          curriculum_citation: 'NCTB Board Textbook - Chapter 5',
          textbook_explanation: 'All C programs must have a valid main() function, explicit variable declarations, and properly terminated control statements.'
        },
        independent_ai_answer: {
          concept_applied: 'TRACE Dual AI Interactive Guidance',
          problem_breakdown: [
            '1. State your specific coding difficulty or question in the input box.',
            '2. Compare NCTB textbook rules with independent AI logic breakdowns.',
            '3. Use the Dual View, RAG Textbook, or Independent AI tabs to study concepts.'
          ],
          pedagogical_justification: 'Dual view reinforces textbook mastery while developing independent algorithmic problem solving.',
          code_solution: ''
        },
        time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      },
    ]);
  }, [examType, currentIndex]);

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
    setChatMessages([
      {
        sender: 'ai',
        text: `👋 Chat history cleared. How can I help you understand this concept or question?`,
        rag_answer: {
          textbook_rule: 'NCTB HSC ICT Chapter 5 Programming Standard',
          curriculum_citation: 'NCTB Board Textbook - Chapter 5',
          textbook_explanation: 'All C programs must have a valid main() function, explicit variable declarations, and properly terminated control statements.'
        },
        independent_ai_answer: {
          concept_applied: 'TRACE AI Tutor Assistance',
          problem_breakdown: [
            '1. Type your question or request a hint below.',
            '2. Toggle between Dual View, RAG Book, or Independent AI tabs.',
            '3. Practice writing and understanding your code.'
          ],
          pedagogical_justification: 'Clear view provides a fresh start for analyzing new concepts.',
          code_solution: ''
        },
        time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      },
    ]);
  };

  const loadItems = async (type) => {
    setIsSubmitted(false);
    setSelectedAnswers({});
    setUserCodeAnswers({});
    setCurrentIndex(0);
    const data = await apiService.getAssessmentItems(type);
    const itemsList = Array.isArray(data) ? data : (data?.items || data?.questions || []);
    setAllItems(itemsList);
    filterItemsByChapter(itemsList, selectedChapter);
  };

  const filterItemsByChapter = (itemsList = [], chap) => {
    const list = Array.isArray(itemsList) ? itemsList : [];
    let result = list;
    if (chap === 'CHAP4') {
      result = list.filter((item) => item.chapter?.includes('Chapter 4'));
    } else if (chap === 'CHAP5') {
      result = list.filter((item) => item.chapter?.includes('Chapter 5'));
    } else if (chap === 'CHAP6') {
      result = list.filter((item) => item.chapter?.includes('Chapter 6'));
    }
    setFilteredItems(result);
  };

  const handleChapterFilter = (chap) => {
    handleSelectChapter(chap);
  };

  const handleSelectChapter = (chap) => {
    setSelectedChapter(chap);
    setCurrentIndex(0);
    filterItemsByChapter(allItems, chap);
  };

  const handleSelectOption = (questionId, optionId) => {
    handleOptionSelect(questionId, optionId);
  };

  const handleOptionSelect = (questionId, optionKey) => {
    setSelectedAnswers((prev) => ({
      ...prev,
      [questionId]: optionKey,
    }));
  };

  const handleCodeChange = (questionId, code) => {
    setUserCodeAnswers((prev) => ({
      ...prev,
      [questionId]: code,
    }));
  };

  const handleSubmitExam = async () => {
    let scoreCount = 0;
    filteredItems.forEach((item) => {
      if (item.type === 'mcq' || item.type === 'concept_mcq') {
        const correctKey = item.correct_option || item.keyed_answer;
        if (selectedAnswers[item.id] === correctKey) {
          scoreCount += 1;
        }
      } else {
        // C / HTML Programming code evaluation
        const studentCode = userCodeAnswers[item.id] || '';
        const src = studentCode.trim();

        // 1. Must be non-empty and edited
        if (src.length > 25 && !src.includes('// Write your C program here')) {
          // 2. Syntax & compiler structure check
          const hasMain = src.includes('main');
          const hasInclude = src.includes('stdio.h') || src.includes('html');
          const openBraces = (src.match(/\{/g) || []).length;
          const closeBraces = (src.match(/\}/g) || []).length;
          const syntaxValid = hasMain && hasInclude && (openBraces === closeBraces);

          if (syntaxValid) {
            // 3. Logic check for specific C problems
            const itemTitle = (item.title || item.question || '').toLowerCase();
            let logicValid = true;

            if (itemTitle.includes('product') || itemTitle.includes('factorial')) {
              if (src.includes('product = 0') || src.includes('product=0') || (!src.includes('*=') && !src.includes('*'))) {
                logicValid = false;
              }
            } else if (itemTitle.includes('sum')) {
              if ((src.includes('sum = 1') && !src.includes('i = 1')) || (!src.includes('+=') && !src.includes('+'))) {
                logicValid = false;
              }
            }

            if (logicValid) {
              scoreCount += 1;
            }
          }
        }
      }
    });

    const total = filteredItems.length || 1;
    const scorePct = Math.round((scoreCount / total) * 100);

    setScoreResult({
      correct: scoreCount,
      total: total,
      pct: scorePct,
    });
    setIsSubmitted(true);

    apiService.logTelemetry('SUBMIT_ASSESSMENT', {
      exam_type: examType,
      score: scorePct,
      answers: selectedAnswers,
      code_answers: userCodeAnswers,
      timestamp: new Date().toISOString(),
    });

    await apiService.submitExam({
      exam_type: examType,
      chapter: selectedChapter,
      score: scorePct,
      answers: selectedAnswers,
      code_answers: userCodeAnswers,
      timestamp: new Date().toISOString(),
    });
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

          <div className="flex flex-wrap items-center gap-1 bg-surface-container-high p-1.5 rounded-xl border border-outline-variant/30 text-xs font-mono">
            <button
              onClick={() => setExamType('pre')}
              className={`px-3.5 py-2 rounded-lg font-bold transition-all ${
                examType === 'pre'
                  ? 'bg-primary text-on-primary shadow-md'
                  : 'text-on-surface-variant hover:text-on-surface'
              }`}
            >
              Pre-Test (Baseline)
            </button>
            <button
              onClick={() => setExamType('post')}
              className={`px-3.5 py-2 rounded-lg font-bold transition-all ${
                examType === 'post'
                  ? 'bg-primary text-on-primary shadow-md'
                  : 'text-on-surface-variant hover:text-on-surface'
              }`}
            >
              Post-Test (+AI Tutor)
            </button>
            <button
              onClick={() => setExamType('transfer')}
              className={`px-3.5 py-2 rounded-lg font-bold transition-all ${
                examType === 'transfer'
                  ? 'bg-primary text-on-primary shadow-md'
                  : 'text-on-surface-variant hover:text-on-surface'
              }`}
            >
              Transfer Test (+AI Tutor)
            </button>
            <button
              onClick={() => setExamType('withdrawal')}
              className={`px-3.5 py-2 rounded-lg font-bold transition-all ${
                examType === 'withdrawal'
                  ? 'bg-amber-500 text-on-surface shadow-md'
                  : 'text-on-surface-variant hover:text-on-surface'
              }`}
            >
              Withdrawal Task (No AI)
            </button>
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
        </div>
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

            {/* Interactive Workspace Code Editor for Coding Tasks */}
            {(currentItem.type === 'c_programming' || currentItem.type === 'html_coding') ? (
              <div className="space-y-2">
                <label className="text-xs font-mono font-bold text-on-surface flex items-center justify-between">
                  <span className="flex items-center gap-1.5">
                    <Code className="w-4 h-4 text-primary" /> Write Your Code Solution ({currentItem.type === 'html_coding' ? 'HTML Markup' : 'C Language'}):
                  </span>
                  <span className="text-emerald-400 font-mono text-[11px] font-bold">Unsolved Student Workspace</span>
                </label>
                <textarea
                  rows={8}
                  value={userCodeAnswers[currentItem.id] !== undefined ? userCodeAnswers[currentItem.id] : currentItem.code_snippet}
                  onChange={(e) => handleCodeChange(currentItem.id, e.target.value)}
                  placeholder="Write your complete code solution here..."
                  className="w-full bg-surface-container-lowest text-on-surface p-4 rounded-xl font-mono text-xs border border-outline-variant/40 focus:border-primary outline-none transition-all shadow-inner leading-relaxed"
                />
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

            {/* Navigation Controls */}
            <div className="flex items-center justify-between pt-4 border-t border-outline-variant/20">
              <button
                onClick={() => setCurrentIndex((prev) => Math.max(0, prev - 1))}
                disabled={currentIndex === 0}
                className="px-4 py-2.5 rounded-xl bg-surface-container-high text-xs text-on-surface-variant hover:text-on-surface disabled:opacity-40 font-bold border border-outline-variant/30"
              >
                Previous Question
              </button>

              {currentIndex < filteredItems.length - 1 ? (
                <button
                  onClick={() => setCurrentIndex((prev) => Math.min(filteredItems.length - 1, prev + 1))}
                  className="px-6 py-2.5 rounded-xl bg-primary text-on-primary font-bold text-xs shadow-md shadow-primary/20 flex items-center gap-1.5 hover:bg-primary-container transition-all"
                >
                  Next Question <ArrowRight className="w-4 h-4" />
                </button>
              ) : (
                <button
                  onClick={handleSubmitExam}
                  className="px-6 py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-600 text-on-surface font-bold text-xs shadow-lg shadow-emerald-500/20 flex items-center gap-1.5 transition-all"
                >
                  Submit Assessment <CheckCircle2 className="w-4 h-4" />
                </button>
              )}
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
                                "{msg.rag_answer.textbook_explanation}"
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

      {/* Exam Result Screen */}
      {isSubmitted && scoreResult && (
        <div className="bg-surface-container p-8 sm:p-12 rounded-2xl border border-outline-variant/30 text-center space-y-6 shadow-2xl max-w-2xl mx-auto">
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
      )}

      {(isSubmitted || !currentItem) && questionIndex}
    </div>
  );
};
