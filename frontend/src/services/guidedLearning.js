export const GUIDED_START_CONCEPT = 'Start with your attempt';
export const GUIDED_START_QUESTION = 'What have you tried so far, and which part would you like to work out next?';
export const GUIDED_BOUNDARY = 'I will guide one small step at a time without giving a complete answer or program.';

const text = (value, limit) => typeof value === 'string' ? value.trim().slice(0, limit) : '';

export function guidedLearning(response) {
  const coaching = response?.coaching;
  const concept = text(coaching?.concept, 400);
  const question = text(coaching?.question, 800);
  const guided = response?.teaching_mode === 'guided' && response?.coaching_policy === 'guided-v1' && Boolean(question);
  if (!guided) {
    return { guided: false, concept: GUIDED_START_CONCEPT, question: GUIDED_START_QUESTION,
      boundaryMessage: GUIDED_BOUNDARY, lineNumber: null, references: [] };
  }

  const references = Array.isArray(response.retrieved_passages)
    ? response.retrieved_passages.flatMap((passage, index) => {
      const source = text(passage?.source_ref, 240);
      if (!/^NCTB HSC ICT(?: \((?:BV|EV)\))? p\.[1-9]\d{0,3}$|^NCTB textbook source [1-5]$/.test(source)) return [];
      const score = passage.similarity_score;
      const sourceNumber = /^source-([1-5])$/.exec(passage.id);
      const number = sourceNumber ? Number(sourceNumber[1]) : index + 1;
      return [{ id: String(number), number, source,
        similarity: typeof score === 'number' && Number.isFinite(score) && score >= 0 && score <= 1 ? score : null }];
    }).slice(0, 5) : [];

  return { guided: true, concept, question,
    boundaryMessage: text(coaching.boundary_message, 500) || GUIDED_BOUNDARY,
    lineNumber: coaching.focus === 'debug' && Number.isInteger(coaching.line_number) && coaching.line_number > 0 && coaching.line_number <= 500
      ? coaching.line_number : null,
    references };
}

export function boundedCoachingHistory(messages) {
  if (!Array.isArray(messages)) return [];
  return messages.flatMap((message) => {
    if (message?.role !== 'user' && message?.role !== 'assistant') return [];
    const content = text(message.text, 400);
    return content ? [{ role: message.role, text: content }] : [];
  }).slice(-6);
}

export function appendCoachingTurn(history, studentText, response) {
  return boundedCoachingHistory([
    ...boundedCoachingHistory(history),
    { role: 'user', text: studentText },
    { role: 'assistant', text: guidedLearning(response).question },
  ]);
}
