import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { ReasoningTracePanel } from '../src/components/TutorPanel/ReasoningTracePanel';
import { AssessmentPage } from '../src/pages/AssessmentPage';

const mocks = vi.hoisted(() => ({ getAssessmentItems: vi.fn(), queryTutor: vi.fn() }));
vi.mock('../src/services/api', () => ({ apiService: mocks }));
vi.mock('../src/context/useAuth', () => ({ useAuth: () => ({ language: 'en', arm: 'REASONING_VISIBLE' }) }));

beforeEach(() => {
  mocks.getAssessmentItems.mockReset().mockResolvedValue({
    available: ['pre', 'post'],
    items: [{ id: 'loop-concept', type: 'mcq', title: 'Loop concept', chapter: 'Chapter 5',
      question: 'Which construct repeats statements?', options: [{ id: 'a', text: 'A loop' }] }],
  });
  mocks.queryTutor.mockReset();
});

afterEach(cleanup);

const conceptNotice = 'The retrieved passages support these concepts; a complete worked solution is not provided.';
const response = (ragAnswer = {}, extra = {}) => ({
  ai_status: 'live',
  rag_answer: {
    textbook_rule: 'Use repetition and a running total.',
    textbook_explanation: 'A for loop repeats its statements and updates the total on each iteration.',
    curriculum_citation: 'NCTB ICT, Chapter 5, printed page 175 [1]',
    ...ragAnswer,
  },
  retrieved_passages: [{
    id: 'loop-p175',
    source_ref: 'NCTB ICT, printed page 175',
    passage: 'The for loop repeats a block of statements.',
    similarity_score: 0.7,
  }],
  independent_ai_answer: { chat_answer: 'Here is an independent explanation of the complete task.' },
  ...extra,
});

const mount = (traceData) => render(
  <ReasoningTracePanel traceData={traceData} availability={{ status: 'available' }} queryText=""
    onQueryChange={vi.fn()} onRequestHelp={vi.fn()} />
);

it('keeps useful textbook concepts, citations and passages visible without claiming a complete worked solution', () => {
  mount(response({ support_level: 'concepts', grounded: true }));

  const badge = screen.getByText('Related textbook concepts');
  expect(badge.className).toContain('text-amber-400');
  expect(screen.getByText(conceptNotice)).toBeTruthy();
  expect(screen.getByText('Use repetition and a running total.')).toBeTruthy();
  expect(screen.getByText('A for loop repeats its statements and updates the total on each iteration.')).toBeTruthy();
  expect(screen.getByText('NCTB ICT, Chapter 5, printed page 175 [1]')).toBeTruthy();
  expect(screen.getByText('[1] NCTB ICT, printed page 175')).toBeTruthy();
  expect(screen.getByText('The for loop repeats a block of statements.')).toBeTruthy();
  expect(screen.queryByText('Curriculum Grounded')).toBeNull();
  expect(screen.queryByText('Not covered by passages')).toBeNull();

  fireEvent.click(screen.getByRole('button', { name: 'Textbook', exact: true }));
  expect(screen.getByText(conceptNotice)).toBeTruthy();
  expect(screen.queryByText('Here is an independent explanation of the complete task.')).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'AI', exact: true }));
  expect(screen.queryByText(conceptNotice)).toBeNull();
  expect(screen.getByText('Here is an independent explanation of the complete task.')).toBeTruthy();
});

it.each([
  ['full', false, 'Curriculum Grounded'],
  ['concepts', false, 'Related textbook concepts'],
  ['none', true, 'Not covered by passages'],
])('uses the explicit %s support level instead of a conflicting legacy boolean', (supportLevel, grounded, label) => {
  mount(response({ support_level: supportLevel, grounded }));
  expect(screen.getByText(label)).toBeTruthy();
  expect(Boolean(screen.queryByText(conceptNotice))).toBe(supportLevel === 'concepts');
});

it.each([
  [undefined, true, 'Curriculum Grounded'],
  [undefined, false, 'Not covered by passages'],
  ['future-level', true, 'Curriculum Grounded'],
  ['future-level', false, 'Not covered by passages'],
])('preserves legacy badges for support level %s and grounded %s in cached answers', (supportLevel, grounded, label) => {
  mount(response({ support_level: supportLevel, grounded }, { cached: true }));
  expect(screen.getByText(label)).toBeTruthy();
  expect(screen.queryByText(conceptNotice)).toBeNull();
});

it('identifies a passage-only fallback without claiming that a generated answer is fully supported', () => {
  mount(response({ support_level: 'full', grounded: true }, { ai_status: 'fallback' }));

  expect(screen.getByText('Retrieved textbook passage')).toBeTruthy();
  expect(screen.getByText('AI generation is unavailable')).toBeTruthy();
  expect(screen.getByText('The for loop repeats a block of statements.')).toBeTruthy();
  expect(screen.getByText('NCTB ICT, Chapter 5, printed page 175 [1]')).toBeTruthy();
  expect(screen.queryByText('Curriculum Grounded')).toBeNull();
  expect(screen.queryByText(conceptNotice)).toBeNull();
});

it.each([
  {},
  { support_level: 'future-level' },
  { support_level: 'future-level', grounded: 'true' },
  { grounded: null },
])('does not turn missing or malformed support metadata %j into a positive grounding claim', (supportMetadata) => {
  mount(response(supportMetadata));

  const badge = screen.getByText('Support not assessed');
  expect(badge.className).toContain('text-on-surface-variant');
  expect(screen.getByText('A for loop repeats its statements and updates the total on each iteration.')).toBeTruthy();
  expect(screen.queryByText('Curriculum Grounded')).toBeNull();
  expect(screen.queryByText(conceptNotice)).toBeNull();
});

it('omits the empty textbook card for a hint while keeping the useful clue', () => {
  mount(response({}, { rag_answer: {}, independent_ai_answer: { chat_answer: 'Think about the value that changes each time.' } }));

  expect(screen.getByText('Think about the value that changes each time.')).toBeTruthy();
  expect(screen.queryByText('NCTB Textbook RAG Answer')).toBeNull();
  expect(screen.queryByText('Curriculum Grounded')).toBeNull();
  expect(screen.queryByText('Support not assessed')).toBeNull();
});

const askInAssessment = async (tutorResponse) => {
  mocks.queryTutor.mockResolvedValue(tutorResponse);
  render(<AssessmentPage />);
  fireEvent.click(await screen.findByRole('button', { name: 'Post-Test (+AI Tutor)', exact: true }));
  const input = await screen.findByRole('textbox', { name: 'Ask the AI assistant for help, hints or logic' });
  fireEvent.change(input, { target: { value: 'How can repetition help with this task?' } });
  fireEvent.keyDown(input, { key: 'Enter' });
};

it('teaches related concepts with citations before showing the coverage limit in the actual assessment tutor', async () => {
  await askInAssessment(response({ support_level: 'concepts', grounded: true }));

  const badge = await screen.findByText('Related textbook concepts');
  expect(badge.className).toContain('text-amber-400');
  const explanation = screen.getByText(/A for loop repeats its statements and updates the total on each iteration\./);
  const notice = screen.getByText(conceptNotice);
  expect(explanation.compareDocumentPosition(notice) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(screen.getByText(/NCTB ICT, Chapter 5, printed page 175 \[1\]/)).toBeTruthy();
  expect(screen.getByText('[1] NCTB ICT, printed page 175')).toBeTruthy();
  expect(screen.getByText('The for loop repeats a block of statements.')).toBeTruthy();
  expect(screen.queryByText('Grounded', { exact: true })).toBeNull();
  expect(screen.queryByText('Curriculum Grounded')).toBeNull();
});

it.each([
  [{ support_level: 'full', grounded: true }, 'Curriculum Grounded'],
  [{ support_level: 'none', grounded: false }, 'Not covered by passages'],
  [{}, 'Support not assessed'],
])('applies support metadata %j to the actual assessment tutor badge', async (supportMetadata, label) => {
  await askInAssessment(response(supportMetadata));

  expect(await screen.findByText(label)).toBeTruthy();
  expect(screen.queryByText(conceptNotice)).toBeNull();
});

it('does not show a grounded textbook card for an empty assessment hint response', async () => {
  await askInAssessment(response({}, { rag_answer: {}, independent_ai_answer: { chat_answer: 'Think about the changing value.' } }));

  expect(await screen.findByText('Think about the changing value.')).toBeTruthy();
  expect(screen.queryByText(/NCTB Textbook RAG Answer/)).toBeNull();
  expect(screen.queryByText('Grounded', { exact: true })).toBeNull();
  expect(screen.queryByText('Curriculum Grounded')).toBeNull();
});
