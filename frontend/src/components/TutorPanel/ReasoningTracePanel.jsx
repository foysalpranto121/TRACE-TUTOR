import { useState } from 'react';
import { Brain, BookOpen, Sparkles, CheckCircle2, Copy, Check, ChevronDown, ChevronUp, Layers, HelpCircle, ShieldCheck, AlertTriangle, FileText, Lock, MessageSquare } from 'lucide-react';
import { apiService } from '../../services/api';
import { ChatMarkdown } from './ChatMarkdown';

const PLACEHOLDERS = {
  dual: 'Ask about your code, an error, or an NCTB concept...',
  rag: 'Ask what the NCTB textbook says about this...',
  independent: 'Ask the AI anything about your code or ICT - it answers on its own...',
};

export const ReasoningTracePanel = ({
  traceData,
  groundedPassage,
  isLoading,
  error,
  errorKind,   // 'policy' when the server refused by rule (a no-AI paper is open), else 'failure'
  onRequestHelp,
  onCopyCode,
}) => {
  const [copied, setCopied] = useState(false);
  const [showPassages, setShowPassages] = useState(true);
  const [queryText, setQueryText] = useState('');
  const [viewTab, setViewTab] = useState('dual'); // 'dual' | 'rag' | 'independent'

  const handleCopy = (code) => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    apiService.logTelemetry('COPY_PASTE', { code_length: code.length });
    if (onCopyCode) onCopyCode(code);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleHelpSubmit = (e) => {
    e.preventDefault();
    if (!queryText.trim()) return;
    // The view the question was asked from travels with it: the server records whether
    // the student reached for the textbook answer or the free AI answer.
    if (onRequestHelp) onRequestHelp(queryText, { view: viewTab });
    setQueryText('');
  };

  const ragData = traceData?.rag_answer || {
    textbook_rule: 'No textbook answer yet',
    curriculum_citation: '',
    textbook_explanation: typeof groundedPassage === 'string' ? groundedPassage : groundedPassage?.passage || '',
  };
  const indepData = traceData?.independent_ai_answer || {};
  const passages = traceData?.retrieved_passages || [];
  const modelLabel = traceData?.model || 'Gemini';
  const isFallback = traceData?.ai_status === 'fallback';

  return (
    <div className="flex flex-col h-full bg-surface-container rounded-2xl border border-outline-variant/30 overflow-hidden shadow-2xl">
      <div className="px-4 py-3 bg-surface-container-high border-b border-outline-variant/30 space-y-2">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-xl bg-primary/15 border border-primary/30 flex items-center justify-center text-primary shrink-0">
            <Brain className="w-4.5 h-4.5" />
          </div>
          <div className="min-w-0 flex-1">
            <h3 className="text-sm font-extrabold text-on-surface font-display truncate">TRACE Tutor</h3>
            <p className="text-[10px] text-on-surface-variant font-medium truncate">RAG grounding + independent reasoning</p>
          </div>
          <div
            title={`Retrieval-augmented answer generated with ${modelLabel}`}
            className={`px-2 py-1 rounded-lg border text-[10px] font-mono font-bold flex items-center gap-1 shrink-0 ${
              isFallback || error ? 'bg-warning/10 border-warning/30 text-warning' : 'bg-success/10 border-success/30 text-success'
            }`}
          >
            <ShieldCheck className="w-3 h-3" />
            <span className="hidden sm:inline">{modelLabel}{traceData?.cached ? ' · cached' : ''}</span>
          </div>
        </div>

        <div className="flex items-center gap-1 bg-surface-container-lowest p-1 rounded-xl border border-outline-variant/30 text-[11px] font-mono">
          {[['dual', 'Dual'], ['rag', 'Textbook'], ['independent', 'AI']].map(([id, label]) => (
            <button
              key={id}
              onClick={() => setViewTab(id)}
              className={`flex-1 py-1.5 px-2 rounded-lg font-bold transition-all press ${
                viewTab === id ? 'bg-primary text-on-primary shadow-glow-sm' : 'text-on-surface-variant hover:text-on-surface'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto overscroll-contain p-5 space-y-5">
        {isLoading && (
          <div className="py-12 flex flex-col items-center justify-center space-y-3">
            <div className="w-10 h-10 border-3 border-primary border-t-transparent rounded-full animate-spin" />
            <span className="text-xs text-primary font-mono font-bold animate-pulse">Retrieving NCTB passages & generating {modelLabel} reasoning...</span>
          </div>
        )}

        {!isLoading && error && (
          errorKind === 'policy' ? (
            // A rule, not an outage: the pre-test and withdrawal task are no-AI papers.
            <div className="bg-amber-500/10 border border-amber-500/30 rounded-xl p-4 text-xs text-amber-500 flex items-start gap-2">
              <Lock className="w-4 h-4 shrink-0 mt-0.5" />
              <div>
                <div className="font-bold">Tutor paused for this paper</div>
                <div className="mt-1 leading-relaxed">{error}</div>
              </div>
            </div>
          ) : (
            <div className="bg-rose-500/10 border border-rose-500/30 rounded-xl p-4 text-xs text-rose-400 flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
              <div>
                <div className="font-bold">AI request failed</div>
                <div className="font-mono mt-1">{error}</div>
              </div>
            </div>
          )
        )}

        {!isLoading && !error && !traceData && (
          <div className="text-xs text-on-surface-variant italic py-6 text-center">
            {viewTab === 'independent'
              ? 'Ask the AI anything, like a chat assistant. It answers from its own knowledge, with a worked solution for your code.'
              : viewTab === 'rag'
                ? 'Ask what the textbook says. You will get an answer grounded in the NCTB passages, with page citations.'
                : 'Ask a question about your code or an NCTB concept. You will get a textbook-grounded answer (with page citations) and an independent AI explanation.'}
          </div>
        )}

        {!isLoading && traceData && (
          <div className="space-y-4">
            {isFallback && (
              <div className="bg-amber-500/10 border border-amber-500/30 rounded-xl p-3 text-[11px] text-amber-500 flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 shrink-0" />
                <span><strong>{modelLabel} did not respond</strong> - showing the retrieved textbook passage only. {traceData.error}</span>
              </div>
            )}

            {(viewTab === 'dual' || viewTab === 'rag') && (
              <div className="bg-sky-500/10 border border-sky-500/30 rounded-xl p-4 space-y-2.5 shadow-sm">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-extrabold text-sky-400 uppercase tracking-wider flex items-center gap-1.5 font-mono">
                    <BookOpen className="w-4 h-4 text-sky-400" /> NCTB Textbook RAG Answer
                  </span>
                  <span className={`text-[10px] font-mono px-2 py-0.5 rounded font-bold border ${
                    ragData.grounded === false ? 'bg-amber-500/20 text-amber-400 border-amber-500/30' : 'bg-sky-500/20 text-sky-300 border-sky-500/30'
                  }`}>
                    {ragData.grounded === false ? 'Not covered by passages' : 'Curriculum Grounded'}
                  </span>
                </div>

                <div className="space-y-1.5">
                  <h4 className="text-xs font-bold text-on-surface">{ragData.textbook_rule}</h4>
                  {ragData.curriculum_citation && <p className="text-xs text-on-surface-variant font-mono text-[11px]">{ragData.curriculum_citation}</p>}
                  <p className="text-xs text-on-surface leading-relaxed italic bg-surface-container p-3 rounded-lg border border-outline-variant/20 whitespace-pre-wrap">
                    {ragData.textbook_explanation}
                  </p>
                </div>

                <div className="pt-1">
                  <button onClick={() => setShowPassages(!showPassages)} className="text-[11px] font-mono font-bold text-sky-400 flex items-center gap-1">
                    <FileText className="w-3.5 h-3.5" /> Retrieved passages ({passages.length}) {showPassages ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                    {traceData.retrieval_backend && <span className="ml-1 text-on-surface-variant font-normal">- {traceData.retrieval_backend} search</span>}
                  </button>
                  {showPassages && (
                    <div className="mt-2 space-y-1.5">
                      {passages.length === 0 && <div className="text-[11px] text-amber-500">No passages in the index yet. Run RAG ingestion from the RAG Inspector page.</div>}
                      {passages.map((p, i) => (
                        <div key={p.id || i} className="bg-surface-container p-2.5 rounded-lg border border-outline-variant/20 text-[11px]">
                          <div className="flex items-center justify-between gap-2 mb-1">
                            <span className="font-mono font-bold text-on-surface">[{i + 1}] {p.source_ref}</span>
                            <span className="font-mono text-sky-400 shrink-0">{Math.round((p.similarity_score || 0) * 100)}%</span>
                          </div>
                          <div className="text-on-surface-variant leading-relaxed line-clamp-4 whitespace-pre-wrap">{p.passage}</div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}

            {(viewTab === 'dual' || viewTab === 'independent') && (
              <div className="bg-purple-500/10 border border-purple-500/30 rounded-xl p-4 space-y-3 shadow-sm">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-extrabold text-purple-400 uppercase tracking-wider flex items-center gap-1.5 font-mono">
                    <Sparkles className="w-4 h-4 text-purple-400" /> Independent AI Reasoning
                  </span>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-purple-500/20 text-purple-300 font-bold border border-purple-500/30">{modelLabel}</span>
                </div>

                {/* The free-form answer: what the model would say in a chat, from its own
                    knowledge, not held to the textbook. The structured breakdown below it
                    is the same answer shown as reasoning steps. */}
                {indepData.chat_answer && (
                  <div className="bg-surface-container p-3.5 rounded-xl border border-outline-variant/30 space-y-1.5">
                    <span className="text-[10px] font-mono uppercase text-purple-400 font-extrabold flex items-center gap-1">
                      <MessageSquare className="w-3.5 h-3.5" /> AI Answer
                    </span>
                    <ChatMarkdown text={indepData.chat_answer} className="text-xs text-on-surface font-medium" />
                  </div>
                )}

                {indepData.concept_applied && (
                  <div className="bg-surface-container p-3 rounded-xl border border-outline-variant/30 flex items-start gap-2.5">
                    <Layers className="w-4 h-4 text-purple-400 shrink-0 mt-0.5" />
                    <div>
                      <span className="text-[10px] font-mono uppercase text-purple-400 font-extrabold block">Concept Applied</span>
                      <span className="text-xs font-bold text-on-surface">{indepData.concept_applied}</span>
                    </div>
                  </div>
                )}

                {indepData.problem_breakdown?.length > 0 && (
                  <div className="space-y-2">
                    <h5 className="text-[11px] font-extrabold text-on-surface uppercase tracking-wider font-mono">Logic & Problem Breakdown:</h5>
                    <div className="space-y-1.5">
                      {indepData.problem_breakdown.map((step, idx) => (
                        <div key={idx} className="bg-surface-container p-3 rounded-xl border border-outline-variant/30 flex items-start gap-2.5 text-xs text-on-surface font-medium">
                          <span className="w-4 h-4 rounded-full bg-purple-500 text-on-surface font-extrabold text-[10px] flex items-center justify-center shrink-0">{idx + 1}</span>
                          <p className="leading-relaxed pt-0.5 whitespace-pre-wrap">{step}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {indepData.pedagogical_justification && (
                  <div className="bg-surface-container p-3.5 rounded-xl border border-outline-variant/30 space-y-1">
                    <span className="text-[10px] font-mono uppercase text-purple-400 font-extrabold flex items-center gap-1">
                      <HelpCircle className="w-3.5 h-3.5" /> Pedagogical Rationale:
                    </span>
                    <p className="text-xs text-on-surface font-medium leading-relaxed whitespace-pre-wrap">{indepData.pedagogical_justification}</p>
                  </div>
                )}

                {indepData.code_solution && (
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between">
                      <span className="text-[11px] font-extrabold text-on-surface font-mono flex items-center gap-1">
                        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> Worked Code Solution
                      </span>
                      <button
                        onClick={() => handleCopy(indepData.code_solution)}
                        className="px-2 py-0.5 rounded-lg bg-surface-container-high hover:bg-surface-container-highest text-[10px] font-mono text-primary font-bold flex items-center gap-1 transition-colors border border-outline-variant/20 shadow-sm"
                      >
                        {copied ? <Check className="w-3 h-3 text-emerald-500" /> : <Copy className="w-3 h-3" />}
                        {copied ? 'Copied!' : 'Copy Code'}
                      </button>
                    </div>
                    <div className="bg-slate-900 dark:bg-surface-container-lowest p-3.5 rounded-xl border border-outline-variant/30 overflow-x-auto shadow-inner">
                      <pre className="font-mono text-xs text-cyan-300 dark:text-primary leading-relaxed whitespace-pre-wrap">{indepData.code_solution}</pre>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      <form onSubmit={handleHelpSubmit} className="p-3.5 bg-surface-container-high border-t border-outline-variant/30 flex gap-2">
        <input
          type="text"
          value={queryText}
          onChange={(e) => setQueryText(e.target.value)}
          placeholder={PLACEHOLDERS[viewTab] || PLACEHOLDERS.dual}
          aria-label="Ask the tutor about your code, an error, or an NCTB concept"
          className="flex-1 bg-surface-container text-on-surface text-xs rounded-xl px-3.5 py-2 border border-outline-variant/30 outline-none focus:border-primary"
        />
        <button type="submit" disabled={!queryText.trim() || isLoading} className="px-4 py-2 rounded-xl bg-primary text-on-primary font-bold text-xs shadow-md disabled:opacity-40 transition-all shrink-0">
          Ask
        </button>
      </form>
    </div>
  );
};
