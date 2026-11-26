import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { ReasoningTracePanel } from '../src/components/TutorPanel/ReasoningTracePanel';
import { AnswerOnlyPanel } from '../src/components/TutorPanel/AnswerOnlyPanel';
import { AssessmentPage } from '../src/pages/AssessmentPage';

const mocks = vi.hoisted(() => ({ arm: 'REASONING_VISIBLE', getAssessmentItems: vi.fn(), queryTutor: vi.fn() }));
vi.mock('../src/services/api', () => ({ apiService: mocks }));
vi.mock('../src/context/useAuth', () => ({ useAuth: () => ({ language: 'en', arm: mocks.arm }) }));

beforeEach(() => {
  mocks.arm = 'REASONING_VISIBLE';
  mocks.getAssessmentItems.mockReset().mockResolvedValue({
    available: ['pre', 'post'],
    items: [{ id: 'loop-concept', type: 'mcq', title: 'Loop concept', chapter: 'Chapter 5',
      question: 'Which construct repeats statements?', options: [{ id: 'a', text: 'A loop' }] }],
  });
  mocks.queryTutor.mockReset();
});
afterEach(cleanup);

const concept = 'A loop repeats one action.';
const question = 'Which value changes in your current attempt?';
const boundary = 'I will guide one small step at a time without giving a complete answer or program.';
const fallbackQuestion = 'What have you tried so far, and which part would you like to work out next?';
const legacy = {
  ai_status: 'live',
  direct_answer: 'LEGACY_FINAL_ANSWER: the answer is 120.',
  code_solution: 'LEGACY_PROGRAM: int main(void) { return 120; }',
  independent_ai_answer: {
    chat_answer: 'LEGACY_CHAT: Here is the complete solution.',
    concept_applied: 'LEGACY_CONCEPT: a complete solution recipe',
    problem_breakdown: ['LEGACY_RECIPE: initialize, multiply, repeat, print the answer.'],
    pedagogical_justification: 'LEGACY_RATIONALE: this proves the whole algorithm.',
    code_solution: 'LEGACY_INDEPENDENT_PROGRAM: int main(void) { return 120; }',
  },
  reasoning_trace: { chat_answer: 'LEGACY_TRACE: the complete answer.', code_solution: 'LEGACY_TRACE_PROGRAM' },
  rag_answer: {
    textbook_rule: 'LEGACY_RULE: follow the entire algorithm.',
    textbook_explanation: 'LEGACY_TEXTBOOK_SOLUTION: multiply all values and print the result.',
    curriculum_citation: 'LEGACY_CITATION: fabricated worked solution page.',
    grounded: true, support_level: 'full',
  },
  grounded_passage: 'LEGACY_GROUNDED_PASSAGE: the answer and full program.',
  retrieved_passages: [{ id: 'loop-p175', source_ref: 'NCTB HSC ICT (BV) p.175',
    passage: 'LEGACY_RAW_PASSAGE: complete worked program appears here.', similarity_score: 0.7 }],
};
const guided = (extra = {}) => ({
  ...legacy,
  teaching_mode: 'guided',
  coaching_policy: 'guided-v1',
  coaching: { concept_id: 'loop', focus: 'attempt', concept, question, boundary_message: boundary, line_number: null },
  ...extra,
});
const panelProps = { availability: { status: 'available' }, queryText: '', onQueryChange: vi.fn(), onRequestHelp: vi.fn() };
const mountPanel = (kind, data) => kind === 'reasoning'
  ? render(<ReasoningTracePanel {...panelProps} traceData={data} />)
  : render(<AnswerOnlyPanel {...panelProps} solutionData={data} />);
const expectNoLegacyAnswer = (container) => {
  expect(container.textContent).not.toContain('LEGACY_');
  expect(container.querySelector('pre')).toBeNull();
  expect(screen.queryByRole('button', { name: /Copy (?:Code|Solution)/i })).toBeNull();
  expect(screen.queryByRole('button', { name: /Direct Solution|Get Fix/i })).toBeNull();
};

it.each(['reasoning', 'answer-only'])('%s workspace panel renders one guided question and ignores legacy answer fields even in a guided response', (kind) => {
  const view = mountPanel(kind, guided());
  expect(screen.getByText(concept)).toBeTruthy();
  expect(screen.getAllByText(question)).toHaveLength(1);
  expect(screen.getByText(boundary)).toBeTruthy();
  expect(screen.getByRole('button', { name: 'Guide my next step', exact: true })).toBeTruthy();
  expectNoLegacyAnswer(view.container);
});

it.each(['reasoning', 'answer-only'])('%s workspace panel replaces a legacy complete-answer payload with the static ask-for-attempt fallback', (kind) => {
  const view = mountPanel(kind, legacy);
  expect(screen.getByText('Start with your attempt')).toBeTruthy();
  expect(screen.getByText(fallbackQuestion)).toBeTruthy();
  expect(screen.queryByText('NCTB HSC ICT (BV) p.175', { exact: false })).toBeNull();
  expectNoLegacyAnswer(view.container);
});

it('renders the brief-arm guided question when the backend omits its concept', () => {
  const view = mountPanel('answer-only', guided({ coaching: { concept: '', question, focus: 'attempt' } }));
  expect(screen.getByText(question)).toBeTruthy();
  expect(screen.queryByText(fallbackQuestion)).toBeNull();
  expectNoLegacyAnswer(view.container);
});

it('rejects arbitrary source strings and never renders a source-provided worked answer', () => {
  const view = mountPanel('reasoning', guided({ retrieved_passages: [
    { source_ref: 'LEGACY_SOURCE_PROGRAM: int main() { return 120; }', passage: 'LEGACY_PASSAGE' },
    { source_ref: 'NCTB HSC ICT (BV) p.175', passage: 'LEGACY_WORKED_EXAMPLE' },
  ] }));
  expect(screen.getByText(/NCTB HSC ICT \(BV\) p\.175/)).toBeTruthy();
  expectNoLegacyAnswer(view.container);
});

it('preserves original passage numbers when the server removes a seed source', () => {
  const view = mountPanel('reasoning', guided({ retrieved_passages: [
    { id: 'source-2', source_ref: 'NCTB HSC ICT (BV) p.175', passage: 'LEGACY_WORKED_EXAMPLE' },
  ] }));
  expect(screen.getByText('[2] NCTB HSC ICT (BV) p.175')).toBeTruthy();
  expectNoLegacyAnswer(view.container);
});

it.each([
  { teaching_mode: 'answer', coaching: { concept, question } },
  { teaching_mode: 'guided', coaching: { concept, question: '' } },
  { teaching_mode: 'guided', coaching_policy: 'legacy', coaching: { concept, question } },
])('rejects incomplete or non-guided coaching metadata %j instead of exposing old solution fields', (metadata) => {
  const view = mountPanel('reasoning', { ...legacy, ...metadata });
  expect(screen.getByText(fallbackQuestion)).toBeTruthy();
  expectNoLegacyAnswer(view.container);
});

it('keeps the same one-step question in Dual, Textbook and AI views while exposing only bibliography references', () => {
  const view = mountPanel('reasoning', guided());
  expect(screen.getByText('Textbook references')).toBeTruthy();
  expect(screen.getByText(/NCTB HSC ICT \(BV\) p\.175/)).toBeTruthy();
  expect(screen.getByText('70% similarity')).toBeTruthy();
  expectNoLegacyAnswer(view.container);

  for (const tab of ['Textbook', 'AI', 'Dual']) {
    fireEvent.click(screen.getByRole('button', { name: tab, exact: true }));
    expect(screen.getAllByText(question)).toHaveLength(1);
    expect(screen.getByText(concept)).toBeTruthy();
    expectNoLegacyAnswer(view.container);
  }
});

it('keeps a guided hint question without requiring a textbook answer or revealing a full recipe', () => {
  const view = mountPanel('reasoning', guided({
    coaching: { concept_id: 'loop', focus: 'attempt', concept, question: 'Which value do you need to keep track of?', boundary_message: boundary },
    rag_answer: {}, retrieved_passages: [],
  }));
  expect(screen.getByText('Which value do you need to keep track of?')).toBeTruthy();
  expect(screen.queryByText('Textbook references')).toBeNull();
  expectNoLegacyAnswer(view.container);
});

const askInAssessment = async (tutorResponse, arm = 'REASONING_VISIBLE', prompt = 'Can you guide my next step?') => {
  mocks.arm = arm;
  mocks.queryTutor.mockResolvedValue(tutorResponse);
  const view = render(<AssessmentPage />);
  fireEvent.click(await screen.findByRole('button', { name: 'Post-Test (+AI Tutor)', exact: true }));
  const input = await screen.findByRole('textbox', { name: /Ask the AI assistant|Share your attempt/i });
  fireEvent.change(input, { target: { value: prompt } });
  fireEvent.keyDown(input, { key: 'Enter' });
  return view;
};

it.each(['REASONING_VISIBLE', 'ANSWER_ONLY'])('%s assessment tutor renders safe coaching instead of any complete-answer fields', async (arm) => {
  const view = await askInAssessment(guided(), arm);
  expect(await screen.findByText(question)).toBeTruthy();
  expect(screen.getByText(concept)).toBeTruthy();
  expect(screen.getAllByText(question)).toHaveLength(1);
  expect(screen.getByRole('button', { name: 'Guide my next step', exact: true })).toBeTruthy();
  expectNoLegacyAnswer(view.container);
});

it.each(['REASONING_VISIBLE', 'ANSWER_ONLY'])('%s assessment tutor blocks malicious legacy complete answers and asks for an attempt', async (arm) => {
  const view = await askInAssessment(legacy, arm);
  expect(await screen.findByText(fallbackQuestion)).toBeTruthy();
  expectNoLegacyAnswer(view.container);
});

it('keeps only safe source references across assessment Textbook and Independent AI views', async () => {
  const view = await askInAssessment(guided());
  expect(await screen.findByText(question)).toBeTruthy();
  expect(screen.getByText(/NCTB HSC ICT \(BV\) p\.175/)).toBeTruthy();
  for (const tab of [/RAG Book/, /Independent AI/, /Dual View/]) {
    fireEvent.click(screen.getByRole('button', { name: tab }));
    expect(screen.getAllByText(question)).toHaveLength(1);
    expectNoLegacyAnswer(view.container);
  }
});
