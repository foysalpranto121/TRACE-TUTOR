import { describeTutorModel } from '../../services/tutorModel';
import { TutorAvailabilityNotice } from './TutorAvailabilityNotice';
import { TutorQuestionForm } from './TutorQuestionForm';
import { Bot, ShieldCheck, AlertTriangle } from 'lucide-react';
import { safeTutorResponse } from '../../services/tutorGuidance';
import { ChatMarkdown } from './ChatMarkdown';

export const AnswerOnlyPanel = ({
  solutionData,
  isLoading,
  error,
  modelMetadata,
  availability,
  onRetryAvailability,
  queryText,
  onQueryChange,
  onRequestHelp,
}) => {
  const response = safeTutorResponse(solutionData);
  const directAnswer = response?.direct_answer || '';
  const modelInfo = describeTutorModel(modelMetadata, solutionData, isLoading);
  const modelLabel = modelInfo.label;

  return (
    <div className="flex flex-col h-full bg-surface-container rounded-2xl border border-outline-variant/30 overflow-hidden shadow-2xl">
      <div className="px-5 py-4 bg-surface-container-high border-b border-outline-variant/30 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-xl bg-amber-500/20 border border-amber-500/30 flex items-center justify-center text-amber-500 shadow-sm">
            <Bot className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-sm font-extrabold text-on-surface flex items-center gap-2">
              AI Assistant <span className="px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-600 dark:text-amber-400 text-[10px] font-mono border border-amber-500/30 font-extrabold">Answer-Only Arm</span>
            </h3>
            <p className="text-[11px] text-on-surface-variant font-medium">Brief guidance for your next step</p>
          </div>
        </div>

        <div title={modelInfo.title} className="px-2.5 py-1 rounded-full bg-surface-container border border-outline-variant/30 text-on-surface-variant text-[11px] font-mono font-bold flex items-center gap-1 shadow-sm">
          <ShieldCheck className="w-3.5 h-3.5 text-primary" />
          {modelLabel}{!isLoading && solutionData?.cached ? ' · cached' : ''}
        </div>
      </div>

      <TutorAvailabilityNotice availability={availability} onRetry={onRetryAvailability} />

      <div className="flex-1 overflow-y-auto p-5 space-y-5">
        {isLoading && (
          <div className="py-12 flex flex-col items-center justify-center space-y-3">
            <div className="w-10 h-10 border-3 border-amber-500 border-t-transparent rounded-full animate-spin" />
            <span role="status" className="text-xs text-amber-500 font-mono font-bold animate-pulse">Generating guidance...</span>
          </div>
        )}

        {!isLoading && error && (
            <div className="bg-rose-500/10 border border-rose-500/30 rounded-xl p-4 text-xs text-rose-400 flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
              <div>
                <div className="font-bold">AI request failed</div>
                <div className="font-mono mt-1">{error}</div>
              </div>
            </div>
        )}

        {!isLoading && response && (
          <div className="space-y-4">
            {response.ai_status === 'fallback' && (
              <div className="bg-amber-500/10 border border-amber-500/30 rounded-xl p-3 text-[11px] text-amber-500">
                AI generation is unavailable. Continue with the available guidance or retry.
              </div>
            )}
            {directAnswer && <ChatMarkdown text={directAnswer} className="text-xs text-on-surface font-medium" />}
          </div>
        )}
      </div>

      <TutorQuestionForm queryText={queryText} onQueryChange={onQueryChange}
        availability={availability} isLoading={isLoading}
        onSubmit={onRequestHelp}
        placeholder="Ask about your attempt or where you are stuck..." label="Ask the tutor for guidance on your code or question" buttonLabel="Get Guidance" answerOnly />
    </div>
  );
};
