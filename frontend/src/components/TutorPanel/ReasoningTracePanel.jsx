import { useState } from 'react';
import { Brain, BookOpen, ShieldCheck, AlertTriangle } from 'lucide-react';
import { describeTutorModel } from '../../services/tutorModel';
import { describeTextbookSupport } from '../../services/textbookSupport';
import { guidedLearning } from '../../services/guidedLearning';
import { TutorAvailabilityNotice } from './TutorAvailabilityNotice';
import { TutorQuestionForm } from './TutorQuestionForm';

export function GuidedLearningCard({ response, showSources = true }) {
  const coaching = guidedLearning(response);
  const support = describeTextbookSupport(response?.rag_answer, response?.ai_status);
  return (
    <div className="space-y-3">
      <div className="bg-surface-container-high p-4 rounded-xl border border-outline-variant/30 space-y-2">
        {coaching.concept && <h4 className="text-xs font-bold text-on-surface">{coaching.concept}</h4>}
        {coaching.lineNumber && <p className="text-[11px] text-on-surface-variant">Focus on line {coaching.lineNumber}.</p>}
        <p className="text-sm text-on-surface leading-relaxed whitespace-pre-wrap">{coaching.question}</p>
      </div>
      <p className="text-[11px] text-on-surface-variant leading-relaxed">{coaching.boundaryMessage}</p>
      {response?.ai_status === 'fallback' && (
        <p className="text-[11px] text-amber-500">AI generation is unavailable. Continue with this guiding question.</p>
      )}
      {showSources && coaching.references.length > 0 && (
        <div className="bg-sky-500/10 border border-sky-500/30 rounded-xl p-3 space-y-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h5 className="text-xs font-bold text-sky-400 flex items-center gap-1.5"><BookOpen className="w-4 h-4" /> Textbook references</h5>
            <span className={`text-[10px] font-mono ${support.tone === 'positive' ? 'text-sky-300' : support.tone === 'caution' ? 'text-amber-400' : 'text-on-surface-variant'}`}>{support.label}</span>
          </div>
          {coaching.references.map((reference, index) => (
            <div key={reference.id + ':' + index} className="flex items-start justify-between gap-2 text-[11px] font-mono">
              <span className="text-on-surface-variant">[{reference.number}] {reference.source}</span>
              {reference.similarity !== null && <span title="Retrieval similarity; this is not answer accuracy or confidence" className="text-sky-400 shrink-0">{Math.round(reference.similarity * 100)}% similarity</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export const ReasoningTracePanel = ({
  traceData, isLoading, error, modelMetadata, availability, onRetryAvailability,
  queryText, onQueryChange, onRequestHelp,
}) => {
  const [viewTab, setViewTab] = useState('dual');
  const modelInfo = describeTutorModel(modelMetadata, traceData, isLoading);
  return (
    <div className="flex flex-col h-full bg-surface-container rounded-2xl border border-outline-variant/30 overflow-hidden shadow-2xl">
      <div className="px-4 py-3 bg-surface-container-high border-b border-outline-variant/30 space-y-2">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-xl bg-primary/15 border border-primary/30 flex items-center justify-center text-primary shrink-0"><Brain className="w-4.5 h-4.5" /></div>
          <div className="min-w-0 flex-1">
            <h3 className="text-sm font-extrabold text-on-surface font-display truncate">TRACE Tutor</h3>
            <p className="text-[10px] text-on-surface-variant font-medium">Guided learning · one next step</p>
          </div>
          <div title={modelInfo.title} className="px-2 py-1 rounded-lg border border-outline-variant/30 text-[10px] font-mono font-bold flex items-center gap-1 shrink-0">
            <ShieldCheck className="w-3 h-3" />
            <span>{modelInfo.label}{!isLoading && traceData?.cached ? ' · cached' : ''}</span>
          </div>
        </div>
        <div className="flex items-center gap-1 bg-surface-container-lowest p-1 rounded-xl border border-outline-variant/30 text-[11px] font-mono">
          {[['dual', 'Dual'], ['rag', 'Textbook'], ['independent', 'AI']].map(([id, label]) => (
            <button key={id} onClick={() => setViewTab(id)} className={`flex-1 py-1.5 px-2 rounded-lg font-bold transition-all ${viewTab === id ? 'bg-primary text-on-primary' : 'text-on-surface-variant hover:text-on-surface'}`}>{label}</button>
          ))}
        </div>
      </div>
      <TutorAvailabilityNotice availability={availability} onRetry={onRetryAvailability} />
      <div className="flex-1 overflow-y-auto overscroll-contain p-5 space-y-4">
        {isLoading ? (
          <p role="status" className="text-xs text-primary font-mono animate-pulse">Preparing your next guiding question...</p>
        ) : (
          <>
            {error && <div className="text-xs text-rose-400 flex gap-2"><AlertTriangle className="w-4 h-4 shrink-0" /><p>AI request failed. Please retry; your draft is preserved.</p></div>}
            <GuidedLearningCard response={traceData} showSources={viewTab !== 'independent'} />
          </>
        )}
      </div>
      <TutorQuestionForm queryText={queryText} onQueryChange={onQueryChange}
        availability={availability} isLoading={isLoading}
        onSubmit={(query) => onRequestHelp(query, { view: viewTab })}
        placeholder="Share your attempt or the step you are stuck on..." label="Ask the tutor for guidance on your next step"
        buttonLabel="Guide my next step" />
    </div>
  );
};
