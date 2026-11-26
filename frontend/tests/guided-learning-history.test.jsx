import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { Workspace } from '../src/pages/Workspace';
import { AssessmentPage } from '../src/pages/AssessmentPage';
import { NCTB_PROBLEMS } from '../src/data/problems';

const mocks = vi.hoisted(() => ({ arm: 'REASONING_VISIBLE', getDashboard: vi.fn(), getAssessmentItems: vi.fn(),
  queryTutor: vi.fn(), getCodeStatus: vi.fn(), logTelemetry: vi.fn() }));
vi.mock('../src/services/api', () => ({ apiService: mocks }));
vi.mock('../src/context/useAuth', () => ({ useAuth: () => ({ user: { id: 42 }, language: 'en', arm: mocks.arm }) }));
vi.mock('../src/context/useTheme', () => ({ useTheme: () => ({ isDark: false }) }));
vi.mock('../src/components/Editor/CodeEditor', () => ({ CodeEditor: () => <div>Code editor</div> }));
vi.mock('../src/components/ui/useCelebrate', () => ({ useCelebrate: () => ({ toast: vi.fn(), levelUp: vi.fn() }) }));

const answer = (turn) => ({ teaching_mode: 'guided', coaching_policy: 'guided-v1', ai_status: 'live',
  coaching: { concept_id: 'attempt', focus: 'attempt', concept: 'Inspect your own attempt.',
    question: `Which change would you try at step ${turn}?`,
    boundary_message: 'I will guide one small step at a time.' },
  direct_answer: 'UNSAFE_LEGACY_FINAL_ANSWER',
  independent_ai_answer: { chat_answer: 'UNSAFE_LEGACY_CHAT', code_solution: 'UNSAFE_LEGACY_PROGRAM' },
});
beforeEach(() => {
  mocks.arm = 'REASONING_VISIBLE';
  mocks.getDashboard.mockReset().mockResolvedValue({ stats: {}, assessments: {}, problems: [], tutor_availability: { available: true } });
  mocks.getAssessmentItems.mockReset().mockResolvedValue({ available: ['pre', 'post', 'transfer'],
    items: [{ id: 'attempt', type: 'mcq', title: 'Attempt question', question: 'Which part are you considering?', options: [] }] });
  mocks.getCodeStatus.mockReset().mockResolvedValue({ ready: true, c: 'Clang' });
  mocks.logTelemetry.mockReset().mockResolvedValue({});
  mocks.queryTutor.mockReset().mockImplementation(async () => answer(mocks.queryTutor.mock.calls.length));
});
afterEach(cleanup);

const mountWorkspace = () => render(<MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}><Workspace /></MemoryRouter>);
const sendWorkspace = async (prompt) => {
  const input = screen.getByRole('textbox', { name: /Ask the tutor/ });
  await waitFor(() => expect(input.readOnly).toBe(false));
  fireEvent.change(input, { target: { value: prompt } });
  fireEvent.click(screen.getByRole('button', { name: 'Guide my next step', exact: true }));
  await waitFor(() => expect(input.value).toBe(''));
};
const history = () => mocks.queryTutor.mock.calls.at(-1)[4].coaching_history;
const expectBoundedHistory = () => {
  const messages = history();
  expect(messages).toHaveLength(6);
  for (const message of messages) {
    expect(['user', 'assistant']).toContain(message.role);
    expect(message.text.length).toBeLessThanOrEqual(400);
    expect(message.text).not.toContain('UNSAFE_LEGACY');
  }
  expect(messages.filter((message) => message.role === 'assistant').map((message) => message.text)).toEqual([
    'Which change would you try at step 2?', 'Which change would you try at step 3?', 'Which change would you try at step 4?',
  ]);
};

it('Workspace sends only the bounded student replies and safe prior questions, then resets when the practice task changes', async () => {
  mountWorkspace();
  for (let turn = 1; turn <= 5; turn++) await sendWorkspace(`My attempt ${turn}: ` + 'x'.repeat(430));
  expectBoundedHistory();
  const task = screen.getByRole('combobox');
  fireEvent.change(task, { target: { value: NCTB_PROBLEMS[1].id } });
  await sendWorkspace('My first attempt on this other task.');
  expect(history()).toEqual([]);
});

it('Workspace clears coaching history when the allocated tutor arm changes', async () => {
  const view = mountWorkspace();
  await sendWorkspace('My first attempt.');
  await sendWorkspace('I changed one value.');
  expect(history()).toHaveLength(2);
  mocks.arm = 'ANSWER_ONLY';
  view.rerender(<MemoryRouter><Workspace /></MemoryRouter>);
  await sendWorkspace('My first attempt in the other panel.');
  expect(history()).toEqual([]);
});

it('Assessment sends bounded safe coaching context without replaying legacy complete-answer fields', async () => {
  render(<AssessmentPage />);
  fireEvent.click(await screen.findByRole('button', { name: 'Post-Test (+AI Tutor)', exact: true }));
  const input = await screen.findByRole('textbox', { name: /Ask the AI assistant|Share your attempt/i });
  for (let turn = 1; turn <= 5; turn++) {
    fireEvent.change(input, { target: { value: `My attempt ${turn}: ` + 'x'.repeat(430) } });
    fireEvent.keyDown(input, { key: 'Enter' });
    await screen.findByText(`Which change would you try at step ${turn}?`);
  }
  expectBoundedHistory();
  fireEvent.click(screen.getByRole('button', { name: 'Transfer Test (+AI Tutor)', exact: true }));
  fireEvent.change(input, { target: { value: 'My first transfer attempt.' } });
  fireEvent.keyDown(input, { key: 'Enter' });
  await screen.findByText('Which change would you try at step 6?');
  expect(history()).toEqual([]);
});
