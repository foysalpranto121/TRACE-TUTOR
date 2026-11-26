export const TUTORING_POLICY = 'no-full-solution-v1';
export const RETRY_GUIDANCE = 'This earlier response needs to be refreshed. Ask again for guidance on your next step.';

const text = (value, limit = 6000) => typeof value === 'string' ? value.slice(0, limit) : '';

// Only responses checked by the current server policy may enter a tutor display.
// Complete-program fields and old aliases are deliberately never copied.
export function safeTutorResponse(response) {
  if (!response || typeof response !== 'object') return null;
  const metadata = Object.fromEntries(['mode', 'model', 'provider', 'ai_status', 'cached', 'cache_tier', 'retrieval_backend']
    .map((key) => [key, response[key]]));
  if (response.tutoring_policy !== TUTORING_POLICY) {
    return { ...metadata, response_needs_retry: true, direct_answer: RETRY_GUIDANCE,
      rag_answer: {}, independent_ai_answer: {}, retrieved_passages: [] };
  }
  const rag = response.rag_answer;
  const independent = response.independent_ai_answer;
  return {
    ...metadata, tutoring_policy: TUTORING_POLICY, response_needs_retry: false,
    direct_answer: text(response.direct_answer),
    rag_answer: rag && typeof rag === 'object' ? {
      textbook_rule: text(rag.textbook_rule), textbook_explanation: text(rag.textbook_explanation),
      curriculum_citation: text(rag.curriculum_citation, 600),
      support_level: rag.support_level, grounded: rag.grounded,
    } : {},
    independent_ai_answer: independent && typeof independent === 'object' ? {
      chat_answer: text(independent.chat_answer), concept_applied: text(independent.concept_applied, 400),
      problem_breakdown: Array.isArray(independent.problem_breakdown)
        ? independent.problem_breakdown.filter((step) => typeof step === 'string').slice(0, 6).map((step) => text(step, 1200)) : [],
      pedagogical_justification: text(independent.pedagogical_justification, 1600),
    } : {},
    retrieved_passages: Array.isArray(response.retrieved_passages) ? response.retrieved_passages.slice(0, 5).map((passage, index) => ({
      id: text(passage?.id, 120) || String(index),
      number: /^source-([1-5])$/.test(passage?.id) ? Number(passage.id.slice(-1)) : index + 1, source_ref: text(passage?.source_ref, 240),
      passage: text(passage?.passage, 2000),
      similarity_score: typeof passage?.similarity_score === 'number' && Number.isFinite(passage.similarity_score)
        ? Math.max(0, Math.min(1, passage.similarity_score)) : 0,
    })) : [],
  };
}

export function boundedTutoringHistory(messages) {
  if (!Array.isArray(messages)) return [];
  return messages.flatMap((message) => {
    if (!['user', 'assistant'].includes(message?.role)) return [];
    const content = text(message.text, 1200).trim();
    return content ? [{ role: message.role, text: content }] : [];
  }).slice(-6);
}

export function appendTutoringTurn(history, studentText, response) {
  const safe = safeTutorResponse(response);
  if (!safe || safe.response_needs_retry) return boundedTutoringHistory(history);
  const explanation = safe.independent_ai_answer.chat_answer || safe.direct_answer || safe.rag_answer.textbook_explanation;
  return boundedTutoringHistory([...boundedTutoringHistory(history),
    { role: 'user', text: studentText }, { role: 'assistant', text: explanation }]);
}
