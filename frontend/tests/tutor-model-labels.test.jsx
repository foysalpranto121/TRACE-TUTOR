import { beforeEach, afterEach, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor, act, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { Dashboard } from '../src/pages/Dashboard';
import { Workspace } from '../src/pages/Workspace';
import { configuredTutorLabel, describeTutorModel } from '../src/services/tutorModel';

const mocks = vi.hoisted(() => ({ arm: 'ANSWER_ONLY', role: 'STUDENT', getDashboard: vi.fn(), getRagStatus: vi.fn(), queryTutor: vi.fn(), getCodeStatus: vi.fn(), logTelemetry: vi.fn() }));
vi.mock('../src/services/api', () => ({ apiService: mocks }));
vi.mock('../src/context/useAuth', () => ({ useAuth: () => ({ user: { id: 42, full_name: 'Student' }, role: mocks.role, arm: mocks.arm, language: 'en' }) }));
vi.mock('../src/context/useTheme', () => ({ useTheme: () => ({ isDark: false }) }));
vi.mock('../src/components/Editor/CodeEditor', () => ({ CodeEditor: () => <div>Code editor</div> }));
vi.mock('../src/components/ui/useCelebrate', () => ({ useCelebrate: () => ({ toast: vi.fn(), levelUp: vi.fn() }) }));
const metadata = (provider = 'openai', model = 'gpt-configured') => ({ provider, primary_model: model, fallback_models: ['backup-model'], configured: true });
const dashboard = (model = metadata()) => ({ stats: {}, assessments: {}, problems: [], recent: [], daily: [], tutor_model: model, tutor_availability: { available: true } });
const mount = (component) => render(<MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>{component}</MemoryRouter>);
beforeEach(() => {
  mocks.arm = 'ANSWER_ONLY'; mocks.role = 'STUDENT';
  mocks.getDashboard.mockReset().mockResolvedValue(dashboard());
  mocks.getRagStatus.mockResolvedValue({ engine: { llm_model: 'outdated-rag-label', vector_count: 0 }, ingest: {} });
  mocks.getCodeStatus.mockResolvedValue({ ready: true }); mocks.logTelemetry.mockResolvedValue({});
  mocks.queryTutor.mockReset();
});
afterEach(cleanup);

for (const [provider, model, label] of [['openai', 'gpt-configured', 'OpenAI · gpt-configured'], ['gemini', 'gemini-configured', 'Gemini · gemini-configured']]) {
  it('Dashboard and both Workspace arms agree for ' + provider, async () => {
    mocks.getDashboard.mockResolvedValue(dashboard(metadata(provider, model)));
    const dash = mount(<Dashboard />); await screen.findByText(label);
    expect(screen.queryByText('outdated-rag-label')).toBeNull(); dash.unmount();
    for (const arm of ['ANSWER_ONLY', 'REASONING_VISIBLE']) {
      mocks.arm = arm; const view = mount(<Workspace />); await screen.findByText(label);
      expect(screen.getByTitle('Configured primary: ' + label)).toBeTruthy(); view.unmount();
    }
  });
}
it('configuration changes update Dashboard on refresh and Workspace on its existing status refresh', async () => {
  const dash = mount(<Dashboard />); await screen.findByText('OpenAI · gpt-configured');
  mocks.getDashboard.mockResolvedValue(dashboard(metadata('gemini', 'gemini-new')));
  fireEvent.click(screen.getByRole('button', { name: /Refresh/i }));
  await screen.findByText('Gemini · gemini-new'); dash.unmount();
  mocks.getDashboard.mockResolvedValue(dashboard()); mount(<Workspace />); await screen.findByText('OpenAI · gpt-configured');
  mocks.getDashboard.mockResolvedValue(dashboard(metadata('gemini', 'gemini-new')));
  await act(async () => { fireEvent.focus(window); }); await screen.findByText('Gemini · gemini-new');
  expect(screen.queryByText('Checking tutor availability…')).toBeNull();
});
it('missing metadata uses a neutral label in both screens', async () => {
  mocks.getDashboard.mockResolvedValue(dashboard(null));
  const dash = mount(<Dashboard />); await screen.findByText('Primary model');
  expect(screen.getByText('AI Tutor')).toBeTruthy(); dash.unmount();
  mount(<Workspace />); await screen.findByTitle('Tutor model metadata unavailable');
  expect(screen.getByText('AI Tutor')).toBeTruthy(); expect(screen.queryByText('Gemini')).toBeNull();
});
it('a selected fallback model is distinguished from the configured primary', async () => {
  mocks.queryTutor.mockResolvedValue({ ai_status: 'live', provider: 'openai', model: 'backup-model', direct_answer: 'Answer' });
  mount(<Workspace />); await screen.findByText('OpenAI · gpt-configured');
  const input = screen.getByRole('textbox', { name: /Ask the tutor/ }); fireEvent.change(input, { target: { value: 'Explain loops' } });
  fireEvent.click(screen.getByRole('button', { name: 'Get Fix' }));
  await screen.findByText('OpenAI · backup-model (fallback model)');
  expect(screen.getByTitle(/Configured primary: OpenAI · gpt-configured; Response model:/)).toBeTruthy();
  await waitFor(() => expect(input.value).toBe(''));
});
it('provider response labels never overwrite the configured primary description', () => {
  const info = describeTutorModel(metadata(), { ai_status: 'live', provider: 'gemini', model: 'gemini-response', cached: true });
  expect(info.label).toBe('Gemini · gemini-response'); expect(info.title).toContain('Configured primary: OpenAI · gpt-configured');
  expect(info.title).toContain('cached answer');
});
it('textbook fallback and legacy responses do not fabricate provider/model provenance', () => {
  expect(describeTutorModel(metadata(), { ai_status: 'fallback', model: 'gpt-configured' }).label).toBe('Textbook fallback');
  expect(describeTutorModel(metadata(), { ai_status: 'live', model: 'legacy-model', cached: true }).label).toBe('legacy-model');
  expect(describeTutorModel(null, { model: 'unverified-model' }).label).toBe('AI Tutor');
  expect(configuredTutorLabel({ provider: 'openai', primary_model: 'gpt-configured', configured: false })).toBe('AI Tutor');
});

it('pending metadata uses the configured primary and never attributes an old cached model to a new request', () => {
  const pending = describeTutorModel(metadata(), { ai_status: 'live', provider: 'gemini', model: 'old-response', cached: true }, true);
  expect(pending.label).toBe('OpenAI · gpt-configured · pending');
  expect(pending.title).toContain('Response pending'); expect(pending.title).not.toContain('old-response');
  expect(describeTutorModel(null, null, true).label).toBe('AI Tutor · pending');
});
it('Workspace clears old response metadata through loading and preserves cached completed provenance', async () => {
  let resolve; const pending = new Promise((done) => { resolve = done; });
  mocks.queryTutor.mockResolvedValueOnce({ ai_status: 'live', provider: 'gemini', model: 'old-response', direct_answer: 'First answer', cached: true }).mockReturnValueOnce(pending);
  mount(<Workspace />); await screen.findByText('OpenAI · gpt-configured');
  const input = screen.getByRole('textbox', { name: /Ask the tutor/ });
  fireEvent.change(input, { target: { value: 'First question' } }); fireEvent.click(screen.getByRole('button', { name: 'Get Fix' }));
  await screen.findByText('Gemini · old-response · cached'); await waitFor(() => expect(input.value).toBe(''));
  fireEvent.change(input, { target: { value: 'Second question' } }); fireEvent.click(screen.getByRole('button', { name: 'Get Fix' }));
  await screen.findByText('OpenAI · gpt-configured · pending'); expect(screen.queryByText('Gemini · old-response · cached')).toBeNull();
  expect(screen.getByRole('status').textContent).toContain('Generating');
  await act(async () => resolve({ ai_status: 'live', provider: 'openai', model: 'new-response', direct_answer: 'Second answer', cached: true }));
  await screen.findByText('OpenAI · new-response · cached');
});
it('teacher AI, Textbook, and Dual tabs preserve response provenance and separate answer content', async () => {
  mocks.arm = 'REASONING_VISIBLE'; mocks.role = 'EXPERT_TEACHER';
  mocks.queryTutor.mockResolvedValue({ ai_status: 'live', provider: 'openai', model: 'actual-response', direct_answer: 'Answer',
    rag_answer: { textbook_rule: 'Textbook rule', textbook_explanation: 'Disposable textbook evidence' },
    independent_ai_answer: { chat_answer: 'Disposable AI answer' }, retrieved_passages: [{ id: 'qa', source_ref: 'QA p.1', passage: 'QA passage' }] });
  mount(<Workspace />); await screen.findByText('OpenAI · gpt-configured');
  fireEvent.change(screen.getByRole('textbox', { name: /Ask the tutor/ }), { target: { value: '7 % 2' } });
  fireEvent.click(screen.getByRole('button', { name: 'Ask', exact: true })); await screen.findByText('Disposable textbook evidence');
  expect(screen.getByText('Disposable AI answer')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Textbook', exact: true })); expect(screen.queryByText('Disposable AI answer')).toBeNull();
  expect(screen.getByText('OpenAI · actual-response')).toBeTruthy();
  expect(screen.getByText('QA passage')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: /Retrieved passages/ })); expect(screen.queryByText('QA passage')).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: /Retrieved passages/ })); expect(screen.getByText('QA passage')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'AI', exact: true })); expect(screen.queryByText('Disposable textbook evidence')).toBeNull();
  expect(screen.getByText('Disposable AI answer')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Dual', exact: true })); expect(screen.getByText('Disposable textbook evidence')).toBeTruthy();
});

it('Dashboard missing scores remain unavailable instead of becoming null percentages or zero marks', async () => {
  mocks.getDashboard.mockResolvedValue({ ...dashboard(), assessments: { pre: { attempts: 1, latest_score: null, best_score: null } } });
  mount(<Dashboard />); await screen.findByText('OpenAI · gpt-configured');
  expect(screen.getAllByText('Score unavailable')).toHaveLength(2);
  expect(screen.queryByText('null%')).toBeNull();
  const exam = within(screen.getByText('Pre-Test (Baseline)').parentElement.parentElement);
  expect(exam.queryByText('0%')).toBeNull(); expect(exam.getByText('Score unavailable')).toBeTruthy();
});
it('Dashboard genuine zero scores display as zero percentages', async () => {
  mocks.getDashboard.mockResolvedValue({ ...dashboard(), assessments: { pre: { attempts: 1, latest_score: 0, best_score: 0 } } });
  mount(<Dashboard />); await screen.findByText('OpenAI · gpt-configured');
  const exam = within(screen.getByText('Pre-Test (Baseline)').parentElement.parentElement);
  expect(exam.getByText('0%')).toBeTruthy();
  expect(within(screen.getByText('সেরা স্কোর').closest('.tint-card')).getByText('0%')).toBeTruthy();
  expect(screen.queryByText('Score unavailable')).toBeNull();
});
