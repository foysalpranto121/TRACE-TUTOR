import { useRef } from 'react';

export function TutorQuestionForm({ queryText, onQueryChange, availability, isLoading, onSubmit, placeholder, label, buttonLabel, answerOnly = false }) {
  const pending = useRef(false);
  const blocked = availability.status !== 'available' || isLoading;
  const submit = async (event) => {
    event.preventDefault();
    if (blocked || pending.current || !queryText.trim()) return;
    const draft = queryText;
    pending.current = true;
    try {
      const accepted = await onSubmit(draft);
      // Preserve edits made while the request was in flight as well as failed drafts.
      if (accepted) onQueryChange((current) => current === draft ? '' : current);
    } catch (_) { /* Caller renders errors; failures always preserve the draft. */ }
    finally { pending.current = false; }
  };
  return (
    <form onSubmit={submit} className="shrink-0 p-3.5 bg-surface-container-high border-t border-outline-variant/30 flex gap-2">
      <input type="text" value={queryText} onChange={(event) => onQueryChange(event.target.value)}
        placeholder={placeholder} aria-label={label} aria-disabled={blocked} readOnly={blocked}
        className="min-w-0 flex-1 bg-surface-container text-on-surface text-xs rounded-xl px-3.5 py-2 border border-outline-variant/30 outline-none focus:border-primary" />
      <button type="submit" disabled={blocked || !queryText.trim()}
        className={'shrink-0 px-4 py-2 rounded-xl font-bold text-xs shadow-md disabled:opacity-40 transition-all ' + (answerOnly ? 'bg-amber-500 text-white' : 'bg-primary text-on-primary')}>
        {buttonLabel}
      </button>
    </form>
  );
}
