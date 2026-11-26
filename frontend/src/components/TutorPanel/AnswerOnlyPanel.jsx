import { Bot, ShieldCheck, AlertTriangle } from 'lucide-react';
import { describeTutorModel } from '../../services/tutorModel';
import { GuidedLearningCard } from './ReasoningTracePanel';
import { TutorAvailabilityNotice } from './TutorAvailabilityNotice';
import { TutorQuestionForm } from './TutorQuestionForm';

export const AnswerOnlyPanel = ({
  solutionData, isLoading, error, modelMetadata, availability, onRetryAvailability,
  queryText, onQueryChange, onRequestHelp,
}) => {
  const modelInfo = describeTutorModel(modelMetadata, solutionData, isLoading);
  return (
    <div className="flex flex-col h-full bg-surface-container rounded-2xl border border-outline-variant/30 overflow-hidden shadow-2xl">
      <div className="px-5 py-4 bg-surface-container-high border-b border-outline-variant/30 flex items-center justify-between gap-2">
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-8 h-8 rounded-xl bg-amber-500/20 border border-amber-500/30 flex items-center justify-center text-amber-500 shrink-0"><Bot className="w-5 h-5" /></div>
          <div>
            <h3 className="text-sm font-extrabold text-on-surface">AI Assistant</h3>
            <p className="text-[11px] text-on-surface-variant font-medium">Guided learning · one next step</p>
          </div>
        </div>
        <div title={modelInfo.title} className="px-2 py-1 rounded-lg bg-surface-container border border-outline-variant/30 text-on-surface-variant text-[10px] font-mono flex items-center gap-1">
          <ShieldCheck className="w-3.5 h-3.5 text-primary shrink-0" />
          {modelInfo.label}{!isLoading && solutionData?.cached ? ' · cached' : ''}
        </div>
      </div>
      <TutorAvailabilityNotice availability={availability} onRetry={onRetryAvailability} />
      <div className="flex-1 overflow-y-auto p-5 space-y-4">
        {isLoading ? (
          <p role="status" className="text-xs text-amber-500 font-mono animate-pulse">Preparing your next guiding question...</p>
        ) : (
          <>
            {error && <div className="text-xs text-rose-400 flex gap-2"><AlertTriangle className="w-4 h-4 shrink-0" /><p>AI request failed. Please retry; your draft is preserved.</p></div>}
            <GuidedLearningCard response={solutionData} />
          </>
        )}
      </div>
      <TutorQuestionForm queryText={queryText} onQueryChange={onQueryChange}
        availability={availability} isLoading={isLoading} onSubmit={onRequestHelp}
        placeholder="Share your attempt or the step you are stuck on..." label="Ask the tutor for guidance on your next step"
        buttonLabel="Guide my next step" answerOnly />
    </div>
  );
};
