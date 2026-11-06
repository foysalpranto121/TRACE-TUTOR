import { Lock, Loader2, AlertTriangle } from 'lucide-react';

export function TutorAvailabilityNotice({ availability, onRetry }) {
  if (availability.status === 'available') return null;
  const checking = availability.status === 'checking';
  const locked = availability.status === 'locked' || (checking && !!availability.examType);
  const Icon = checking ? Loader2 : locked ? Lock : AlertTriangle;
  const paper = availability.examType === 'pre' ? 'pre-test' : availability.examType === 'withdrawal' ? 'withdrawal task' : 'paper';
  return (
    <div role="status" aria-live="polite" className="shrink-0 m-3 rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-on-surface flex items-start gap-2">
      <Icon className={'w-4 h-4 shrink-0 mt-0.5 ' + (checking ? 'animate-spin' : '')} />
      <div className="min-w-0">
        <p className="font-bold">{locked ? 'Tutor temporarily unavailable' : checking ? 'Checking tutor availability…' : 'Could not verify tutor availability'}</p>
        <p className="mt-1 leading-relaxed">{locked
          ? 'Your ' + paper + ' is still in progress. Please submit your paper before using the AI Tutor.'
          : checking ? 'Please wait before sending a question. Your draft will stay here.'
            : 'Please retry the availability check. Your draft has been preserved.'}</p>
        {checking && locked && <p className="mt-1">Checking tutor availability…</p>}
        {!checking && <button type="button" onClick={onRetry} className="mt-2 underline font-semibold">{locked ? 'Refresh status' : 'Retry'}</button>}
      </div>
    </div>
  );
}
