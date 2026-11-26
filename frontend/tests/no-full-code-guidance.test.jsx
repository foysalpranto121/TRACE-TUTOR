import { beforeEach, afterEach, expect, it, vi } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ReasoningTracePanel } from '../src/components/TutorPanel/ReasoningTracePanel';
import { AnswerOnlyPanel } from '../src/components/TutorPanel/AnswerOnlyPanel';
import { AssessmentPage } from '../src/pages/AssessmentPage';
import { Workspace } from '../src/pages/Workspace';
import { safeTutorResponse, appendTutoringTurn, boundedTutoringHistory, RETRY_GUIDANCE } from '../src/services/tutorGuidance';

const mocks = vi.hoisted(() => ({ arm: 'REASONING_VISIBLE', getAssessmentItems: vi.fn(), queryTutor: vi.fn(),
  getDashboard: vi.fn(), getCodeStatus: vi.fn(), logTelemetry: vi.fn() }));
vi.mock('../src/services/api', () => ({ apiService: mocks }));
vi.mock('../src/context/useAuth', () => ({ useAuth: () => ({ user: { id: 42 }, language: 'en', arm: mocks.arm }) }));
vi.mock('../src/components/Editor/CodeEditor', () => ({ CodeEditor: () => <div>Code editor</div> }));
vi.mock('../src/components/ui/useCelebrate', () => ({ useCelebrate: () => ({ toast: vi.fn(), levelUp: vi.fn() }) }));

const program = 'LEGACY_WHOLE_PROGRAM #include <stdio.h> int main(void) { return 120; }';
const textbook = 'The textbook describes repetition under a condition; use that idea to inspect your loop.';
const explanation = 'Your accumulator currently starts at zero, so multiplication cannot change it. Think about a starting value that preserves multiplication, and try changing only that part.';
const next = 'For your attempt, what should the stored product represent after one iteration?';
const answer = (extra = {}) => ({
  tutoring_policy: 'no-full-solution-v1', ai_status: 'live',
  direct_answer: 'Inspect the initial value in your own attempt and explain what one multiplication does.',
  rag_answer: { textbook_rule: 'Repetition', textbook_explanation: textbook,
    curriculum_citation: '[1] NCTB HSC ICT p.182', support_level: 'concepts', grounded: true },
  independent_ai_answer: { chat_answer: `${explanation}\n\n${next}`, concept_applied: 'Accumulation',
    problem_breakdown: ['Trace only the first multiplication in your current attempt.'],
    pedagogical_justification: 'Starting values affect every repeated update.', code_solution: program },
  code_solution: program, answer: program, reasoning_trace: { code_solution: program }, grounded_passage: program,
  retrieved_passages: [{ id: 'source-1', source_ref: 'NCTB HSC ICT p.182', passage: 'A loop repeats statements.', similarity_score: 0.7 }],
  ...extra,
});
const props = { availability: { status: 'available' }, queryText: '', onQueryChange: vi.fn(), onRequestHelp: vi.fn() };
const mountPanel = (kind, response) => kind === 'brief'
  ? render(<AnswerOnlyPanel {...props} solutionData={response} />)
  : render(<ReasoningTracePanel {...props} traceData={response} />);

beforeEach(() => {
  mocks.arm = 'REASONING_VISIBLE';
  mocks.getAssessmentItems.mockReset().mockResolvedValue({ available: ['pre', 'post'],
    items: [{ id: 'product', type: 'mcq', title: 'Product from 1 to N', chapter: 'Chapter 5',
      question: 'Find the product using a loop.', options: [{ id: 'a', text: 'A loop' }] }] });
  mocks.queryTutor.mockReset().mockResolvedValue(answer());
  mocks.getDashboard.mockReset().mockResolvedValue({ stats: {}, assessments: {}, problems: [], tutor_availability: { available: true } });
  mocks.getCodeStatus.mockResolvedValue({ ready: true });
  mocks.logTelemetry.mockResolvedValue({});
});
afterEach(cleanup);

it('keeps contextual feedback, a meaningful next step and separate textbook and independent guidance', () => {
  const view = mountPanel('dual', answer());
  expect(screen.getByText(explanation)).toBeTruthy();
  expect(screen.getByText(next)).toBeTruthy();
  expect(screen.getByText(textbook)).toBeTruthy();
  expect(screen.getByText('Trace only the first multiplication in your current attempt.')).toBeTruthy();
  expect(view.container.textContent).not.toContain('LEGACY_WHOLE_PROGRAM');
  expect(screen.queryByRole('button', { name: /Copy Code|Copy Solution/ })).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Textbook', exact: true }));
  expect(screen.getByText(textbook)).toBeTruthy();
  expect(screen.queryByText(explanation)).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'AI', exact: true }));
  expect(screen.getByText(explanation)).toBeTruthy();
  expect(screen.queryByText(textbook)).toBeNull();
});

it.each(['dual', 'brief'])('does not render whole-program fields in the %s panel', (kind) => {
  const view = mountPanel(kind, answer());
  expect(view.container.textContent).not.toContain('LEGACY_WHOLE_PROGRAM');
  expect(screen.queryByText(/Worked Code Solution|Direct Solution Output/)).toBeNull();
  expect(view.container.querySelector('pre')).toBeNull();
});

it.each(['dual', 'brief'])('replaces unmarked cached answers with a retry notice in the %s panel', (kind) => {
  const response = answer({ tutoring_policy: undefined, cached: true, direct_answer: program });
  response.independent_ai_answer.chat_answer = program;
  response.rag_answer.textbook_explanation = program;
  const view = mountPanel(kind, response);
  expect(screen.getByText(RETRY_GUIDANCE)).toBeTruthy();
  expect(view.container.textContent).not.toContain('LEGACY_WHOLE_PROGRAM');
});

it('can render a reviewed isolated syntax illustration while excluding any full-program field', () => {
  const response = answer();
  response.independent_ai_answer.chat_answer = 'This operator updates an existing value:\n\n```c\nvalue *= factor;\n```\n\nExplain what would change in your attempt.';
  const view = mountPanel('dual', response);
  expect(screen.getByText('value *= factor;')).toBeTruthy();
  expect(view.container.querySelectorAll('pre')).toHaveLength(1);
  expect(view.container.textContent).not.toContain('LEGACY_WHOLE_PROGRAM');
});

const openAssessment = async () => {
  render(<AssessmentPage />);
  fireEvent.click(await screen.findByRole('button', { name: 'Post-Test (+AI Tutor)', exact: true }));
  return screen.findByRole('textbox', { name: 'Ask the AI assistant for help, hints or logic' });
};
const ask = async (input, text) => {
  fireEvent.change(input, { target: { value: text } });
  fireEvent.keyDown(input, { key: 'Enter' });
};

it.each(['REASONING_VISIBLE', 'ANSWER_ONLY'])('assessment %s preserves guidance and never appends a whole worked solution', async (arm) => {
  mocks.arm = arm;
  const input = await openAssessment();
  await ask(input, 'Give me the whole code');
  await screen.findByText(arm === 'ANSWER_ONLY' ? answer().direct_answer : explanation);
  expect(document.body.textContent).not.toContain('LEGACY_WHOLE_PROGRAM');
  expect(screen.queryByRole('button', { name: 'Direct Solution', exact: true })).toBeNull();
  if (arm === 'REASONING_VISIBLE') {
    expect(screen.getByText(textbook, { exact: false })).toBeTruthy();
    expect(screen.getByText(next)).toBeTruthy();
  } else {
    expect(screen.getByRole('button', { name: 'Guide Me', exact: true })).toBeTruthy();
    expect(screen.queryByText(textbook, { exact: false })).toBeNull();
  }
});

it('assessment sends recent contextual guidance without old code aliases and clears that history', async () => {
  const input = await openAssessment();
  await ask(input, 'My product starts at zero');
  await screen.findByText(explanation);
  await ask(input, 'I changed the start; what should I check next?');
  await waitFor(() => expect(mocks.queryTutor).toHaveBeenCalledTimes(2));
  const history = mocks.queryTutor.mock.calls[1][4].tutoring_history;
  expect(history).toEqual([{ role: 'user', text: 'My product starts at zero' },
    { role: 'assistant', text: `${explanation}\n\n${next}` }]);
  expect(JSON.stringify(history)).not.toContain('LEGACY_WHOLE_PROGRAM');
  await waitFor(() => expect(screen.queryByText(/TRACE AI is retrieving/)).toBeNull());
  fireEvent.click(screen.getByRole('button', { name: 'Clear Chat' }));
  await ask(input, 'Start a new discussion');
  await waitFor(() => expect(mocks.queryTutor).toHaveBeenCalledTimes(3));
  expect(mocks.queryTutor.mock.calls[2][4].tutoring_history).toEqual([]);
});

it('clearing assessment chat ignores an older pending response', async () => {
  let resolve;
  mocks.queryTutor.mockReturnValueOnce(new Promise((done) => { resolve = done; }));
  const input = await openAssessment();
  await ask(input, 'Please guide this attempt');
  await waitFor(() => expect(mocks.queryTutor).toHaveBeenCalledTimes(1));
  fireEvent.click(screen.getByRole('button', { name: 'Clear Chat' }));
  await act(async () => resolve(answer()));
  expect(screen.queryByText(explanation)).toBeNull();
});

it('workspace sends only bounded guidance history and resets when the tutor arm changes', async () => {
  const view = render(<MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}><Workspace /></MemoryRouter>);
  const input = await screen.findByRole('textbox', { name: /Ask the tutor/ });
  await waitFor(() => expect(input.readOnly).toBe(false));
  fireEvent.change(input, { target: { value: 'My accumulator is zero' } });
  fireEvent.click(screen.getByRole('button', { name: 'Ask', exact: true }));
  await screen.findByText(explanation);
  await waitFor(() => expect(input.value).toBe(''));
  fireEvent.change(input, { target: { value: 'Help me inspect the next repetition' } });
  fireEvent.click(screen.getByRole('button', { name: 'Ask', exact: true }));
  await waitFor(() => expect(mocks.queryTutor).toHaveBeenCalledTimes(2));
  expect(mocks.queryTutor.mock.calls[1][4].tutoring_history).toEqual([
    { role: 'user', text: 'My accumulator is zero' }, { role: 'assistant', text: `${explanation}\n\n${next}` }]);
  await waitFor(() => expect(input.value).toBe(''));
  mocks.arm = 'ANSWER_ONLY';
  view.rerender(<MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}><Workspace /></MemoryRouter>);
  const briefInput = screen.getByRole('textbox', { name: /Ask the tutor/ });
  fireEvent.change(briefInput, { target: { value: 'A different short hint' } });
  fireEvent.click(screen.getByRole('button', { name: 'Get Guidance', exact: true }));
  await waitFor(() => expect(mocks.queryTutor).toHaveBeenCalledTimes(3));
  expect(mocks.queryTutor.mock.calls[2][4].tutoring_history).toEqual([]);
});

it('bounds history and discards legacy response text rather than replaying an old solution', () => {
  const many = Array.from({ length: 15 }, () => ({ role: 'user', text: 'x'.repeat(2000) }));
  expect(boundedTutoringHistory(many)).toHaveLength(6);
  expect(boundedTutoringHistory(many).every((message) => message.text.length <= 1200)).toBe(true);
  expect(appendTutoringTurn([], 'Question', answer({ tutoring_policy: undefined }))).toEqual([]);
  expect(safeTutorResponse(answer()).code_solution).toBeUndefined();
  expect(safeTutorResponse(answer()).independent_ai_answer.code_solution).toBeUndefined();
});

it('retains original source numbers when seed references were removed by the server', () => {
  const response = answer({ retrieved_passages: [{ id: 'source-2', source_ref: 'NCTB HSC ICT p.166', passage: 'Operators act on values.' }] });
  mountPanel('dual', response);
  expect(screen.getByText('[2] NCTB HSC ICT p.166')).toBeTruthy();
  expect(screen.queryByText('[1] NCTB HSC ICT p.166')).toBeNull();
});
