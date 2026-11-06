import { beforeEach, afterEach, describe, it, expect, vi } from 'vitest';
import { useState } from 'react';
import { render, screen, fireEvent, cleanup, waitFor, act, within } from '@testing-library/react';
import { MemoryRouter, Routes, Route, useLocation, useNavigate } from 'react-router-dom';
import { HeaderSearch } from '../src/components/Layout/HeaderSearch';
import { AppShell } from '../src/components/Layout/AppShell';
import { Dashboard } from '../src/pages/Dashboard';
import { Workspace } from '../src/pages/Workspace';
import { Profile } from '../src/pages/Profile';
import { AssessmentPage } from '../src/pages/AssessmentPage';
import { NCTB_PROBLEMS } from '../src/data/problems';
import { buildLearningCatalog, searchLearningCatalog } from '../src/services/learningSearch';

const mocks = vi.hoisted(() => ({
  user: { id: 42, username: 'student', full_name: 'Student', role: 'STUDENT' },
  language: 'en', role: 'STUDENT', loadLearningCatalog: vi.fn(),
  getDashboard: vi.fn(), getRagStatus: vi.fn(), getCodeStatus: vi.fn(), logTelemetry: vi.fn(),
  getAssessmentItems: vi.fn(), searchCurriculum: vi.fn(), queryTutor: vi.fn(),
}));
vi.mock('../src/services/learningSearch', async (importOriginal) => ({
  ...await importOriginal(), loadLearningCatalog: mocks.loadLearningCatalog,
}));
vi.mock('../src/services/api', () => ({ apiService: mocks }));
vi.mock('../src/context/useAuth', () => ({ useAuth: () => ({
  user: mocks.user, role: mocks.role, language: mocks.language, arm: 'ANSWER_ONLY',
  logout: vi.fn(), toggleArm: vi.fn(), setLanguage: vi.fn(), updateProfile: vi.fn(),
  changePassword: vi.fn(), setArm: vi.fn(), uploadAvatar: vi.fn(), removeAvatar: vi.fn(), withdraw: vi.fn(),
}) }));
vi.mock('../src/context/useTheme', async (importOriginal) => ({
  ...await importOriginal(), useTheme: () => ({
    isDark: false, theme: 'light', toggleTheme: vi.fn(), setTheme: vi.fn(),
    fxChoice: 'minimal', setFx: vi.fn(), systemReducedMotion: false,
  }),
}));
vi.mock('../src/components/Editor/CodeEditor', () => ({
  CodeEditor: ({ initialCode, activeProblem, onCodeChange }) => {
    const [code, setCode] = useState(initialCode);
    return <textarea aria-label="Code editor" value={code} data-problem={activeProblem.id} onChange={(event) => {
      setCode(event.target.value); onCodeChange(event.target.value);
    }} />;
  },
}));
vi.mock('../src/components/ui/useCelebrate', () => ({ useCelebrate: () => ({ toast: vi.fn(), levelUp: vi.fn() }) }));

const catalog = buildLearningCatalog(NCTB_PROBLEMS);
const task = NCTB_PROBLEMS.find((problem) => problem.id === 'prob_c_cond_102');
const taskEntry = () => catalog.find((entry) => entry.id === task.id);
const dashboard = () => ({
  stats: {}, assessments: {}, problems: [], recent: [], daily: [],
  tutor_model: { provider: 'openai', primary_model: 'gpt-5-mini', fallback_models: [], configured: true },
  tutor_availability: { available: true },
});
const deferred = () => {
  let resolve;
  let reject;
  const promise = new Promise((done, fail) => { resolve = done; reject = fail; });
  return { promise, resolve, reject };
};
const Location = () => { const location = useLocation(); return <output aria-label="Current route">{location.pathname}{location.search}</output>; };
const HistoryBack = () => { const navigate = useNavigate(); return <button onClick={() => navigate(-1)}>Go back</button>; };
const mount = () => render(
  <MemoryRouter initialEntries={['/profile']} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
    <HeaderSearch /><button>Outside search</button><Location />
  </MemoryRouter>,
);
const input = () => screen.getByRole('combobox', { name: 'Search topics and tasks' });
const query = (value) => fireEvent.change(input(), { target: { value } });
const options = () => screen.getAllByRole('option');
const ready = () => screen.findByRole('listbox', { name: 'Topics and tasks' });
const route = () => screen.getByLabelText('Current route').textContent;

beforeEach(() => {
  mocks.user = { id: 42, username: 'student', full_name: 'Student', role: 'STUDENT' };
  mocks.role = 'STUDENT'; mocks.language = 'en';
  mocks.loadLearningCatalog.mockReset().mockResolvedValue(catalog);
  mocks.getDashboard.mockReset().mockResolvedValue(dashboard());
  mocks.getRagStatus.mockReset().mockResolvedValue({ engine: { vector_count: 0 }, ingest: {} });
  mocks.getCodeStatus.mockReset().mockResolvedValue({ ready: true, c: 'Clang' });
  mocks.logTelemetry.mockReset().mockResolvedValue({});
  mocks.getAssessmentItems.mockReset().mockResolvedValue({ items: [], available: ['pre'] });
  mocks.searchCurriculum.mockReset(); mocks.queryTutor.mockReset();
});
afterEach(cleanup);

describe('learning catalog search', () => {
  it('indexes existing practice tasks and topics without assessment or answer material', () => {
    for (const problem of NCTB_PROBLEMS) {
      const entry = catalog.find((item) => item.id === problem.id);
      expect(entry).toMatchObject({ title: problem.title, type: problem.lang === 'html' ? 'HTML task' : 'C task', locked: false });
      expect(entry.destination).toBe('/workspace?problem=' + encodeURIComponent(problem.id));
      expect(entry).not.toHaveProperty('starterCode');
      expect(entry).not.toHaveProperty('sample_cases');
      expect(entry).not.toHaveProperty('correct_answer');
    }
    expect(catalog.some((entry) => entry.type === 'Topic')).toBe(true);
    expect(catalog.every((entry) => entry.destination.startsWith('/workspace?problem='))).toBe(true);
  });
  it.each([
    ['loop', 'prob_c_loop_101'],
    ['  eVeN   or ODd  ', 'prob_c_cond_102'], ['Factorial', 'prob_c_fact_103'],
    ['prob_html_table_201', 'prob_html_table_201'], ['HTML Tables', 'prob_html_table_201'],
    ['Conditionals', 'prob_c_cond_102'], ['Chapter 4', 'prob_html_table_201'],
    ['ধনাত্মক', 'prob_c_loop_101'],
  ])('finds matching title, identifier, chapter, or topic for %s', (value, expectedId) => {
    expect(searchLearningCatalog(catalog, value).some((entry) => entry.id === expectedId)).toBe(true);
  });
  it('handles empty queries and unknown text without inventing results', () => {
    expect(searchLearningCatalog(catalog, '   ')).toEqual([]);
    expect(searchLearningCatalog(catalog, 'no-such-topic-xyzzzz')).toEqual([]);
  });
  it('a topic opens its first available task and cannot unlock an entirely locked topic', () => {
    const original = NCTB_PROBLEMS.filter((problem) => problem.skill === 'Loops & Accumulation');
    const mixed = buildLearningCatalog(original.map((problem, index) => ({ ...problem, locked: index === 0 })));
    const topic = mixed.find((entry) => entry.type === 'Topic');
    expect(topic.locked).toBe(false);
    expect(topic.destination).toBe('/workspace?problem=' + original[1].id);
    const locked = buildLearningCatalog(original.map((problem) => ({ ...problem, locked: true })));
    expect(locked.find((entry) => entry.type === 'Topic')).toMatchObject({ locked: true, destination: '' });
  });
});

describe('HeaderSearch', () => {
  it('starts closed and renders real categorized results after typing', async () => {
    mount(); expect(input().getAttribute('aria-expanded')).toBe('false');
    expect(screen.queryByRole('listbox')).toBeNull();
    query('even'); await ready();
    const row = screen.getByRole('option', { name: new RegExp(task.title.replace(/[()]/g, '\\$&')) });
    expect(within(row).getByText(/C task/)).toBeTruthy();
    expect(row.textContent).toContain(task.chapter);
    query('factorial'); await screen.findByRole('option', { name: /Factorial/ });
    expect(mocks.loadLearningCatalog).toHaveBeenCalledTimes(1);
    expect(mocks.getAssessmentItems).not.toHaveBeenCalled();
    expect(mocks.searchCurriculum).not.toHaveBeenCalled();
  });
  it('mouse selection navigates to the exact practice task and closes the popup', async () => {
    mount(); query(task.id); await ready();
    fireEvent.click(screen.getByRole('option', { name: /Even or Odd/ }));
    expect(route()).toBe(taskEntry().destination); expect(screen.queryByRole('listbox')).toBeNull();
  });
  it('Enter opens the first available result when none has been highlighted', async () => {
    mount(); query(task.id); await ready();
    fireEvent.keyDown(input(), { key: 'Enter' });
    expect(route()).toBe(taskEntry().destination);
  });
  it('a specific task title ranks above a broadly matching topic and Enter opens that task', async () => {
    const results = searchLearningCatalog(catalog, 'Factorial');
    expect(results[0].id).toBe('prob_c_fact_103');
    expect(results.some((entry) => entry.type === 'Topic' && entry.title === 'Loops & Accumulation')).toBe(true);
    mount(); query('Factorial'); await ready();
    expect(options()[0].textContent).toContain('Factorial of a Number');
    fireEvent.keyDown(input(), { key: 'Enter' });
    expect(route()).toBe('/workspace?problem=prob_c_fact_103');
  });
  it('unhighlighted Enter skips a locked result, while explicitly selecting it cannot navigate', async () => {
    const available = catalog.find((entry) => entry.id === 'prob_c_fact_103');
    mocks.loadLearningCatalog.mockResolvedValue([
      { ...taskEntry(), title: 'Shared locked task', locked: true },
      { ...available, title: 'Shared available task' },
    ]);
    const firstMount = mount(); query('Shared'); await ready();
    fireEvent.keyDown(input(), { key: 'Enter' }); expect(route()).toBe(available.destination);
    firstMount.unmount();
    mount(); query('Shared'); await ready(); fireEvent.keyDown(input(), { key: 'ArrowDown' });
    expect(screen.getByRole('option', { name: /Shared locked task/ }).getAttribute('aria-selected')).toBe('true');
    fireEvent.keyDown(input(), { key: 'Enter' }); expect(route()).toBe('/profile');
  });
  it('ArrowDown and ArrowUp expose the highlighted result and Enter opens it', async () => {
    mount(); query('html'); await ready();
    fireEvent.keyDown(input(), { key: 'ArrowDown' });
    const first = options().find((row) => row.getAttribute('aria-selected') === 'true');
    expect(first).toBeTruthy(); expect(input().getAttribute('aria-activedescendant')).toBe(first.id);
    fireEvent.keyDown(input(), { key: 'ArrowDown' });
    const second = options().find((row) => row.getAttribute('aria-selected') === 'true');
    expect(second.id).not.toBe(first.id);
    fireEvent.keyDown(input(), { key: 'ArrowUp' });
    expect(first.getAttribute('aria-selected')).toBe('true');
    const expected = searchLearningCatalog(catalog, 'html')[options().indexOf(first)].destination;
    fireEvent.keyDown(input(), { key: 'Enter' }); expect(route()).toBe(expected);
  });
  it('Escape, outside pointer interaction, and an empty query dismiss the popup', async () => {
    mount(); query('even'); await ready();
    fireEvent.keyDown(input(), { key: 'Escape' }); expect(screen.queryByRole('listbox')).toBeNull();
    fireEvent.focus(input()); await ready();
    fireEvent.pointerDown(screen.getByRole('button', { name: 'Outside search' })); expect(screen.queryByRole('listbox')).toBeNull();
    query('factorial'); await ready(); query(''); expect(screen.queryByRole('listbox')).toBeNull();
    expect(input().getAttribute('aria-expanded')).toBe('false');
  });
  it('shows a loading state and cannot navigate before the catalog is ready', async () => {
    const pending = deferred(); mocks.loadLearningCatalog.mockReturnValue(pending.promise);
    mount(); query('even'); expect(await screen.findByText('Loading topics and tasks…')).toBeTruthy();
    fireEvent.keyDown(input(), { key: 'Enter' }); expect(route()).toBe('/profile');
    await act(async () => pending.resolve(catalog)); await ready();
    expect(screen.queryByText('Loading topics and tasks…')).toBeNull();
  });
  it('does not reopen after Escape while its catalog request was pending', async () => {
    const pending = deferred(); mocks.loadLearningCatalog.mockReturnValue(pending.promise);
    mount(); query('even'); await screen.findByText('Loading topics and tasks…');
    fireEvent.keyDown(input(), { key: 'Escape' });
    await act(async () => pending.resolve(catalog));
    expect(screen.queryByRole('listbox')).toBeNull(); expect(input().getAttribute('aria-expanded')).toBe('false');
    expect(route()).toBe('/profile');
  });
  it('uses the latest query when lazy loading completes', async () => {
    const pending = deferred(); mocks.loadLearningCatalog.mockReturnValue(pending.promise);
    mount(); query('even'); query('factorial');
    await act(async () => pending.resolve(catalog)); await ready();
    expect(screen.getByRole('option', { name: /Factorial/ })).toBeTruthy();
    expect(screen.queryByRole('option', { name: /Even or Odd/ })).toBeNull();
    expect(input().value).toBe('factorial');
  });
  it('shows an empty result message for unmatched queries', async () => {
    mount(); query('not-a-real-task-xyzzzz');
    expect(await screen.findByText('No matching topics or tasks found.')).toBeTruthy();
    fireEvent.keyDown(input(), { key: 'Enter' }); expect(route()).toBe('/profile');
  });
  it('retries a failed catalog load without erasing the query', async () => {
    mocks.loadLearningCatalog.mockRejectedValueOnce(new Error('Catalog failed'));
    mount(); query('even'); await screen.findByText('Search is unavailable. Please try again.');
    expect(input().value).toBe('even'); fireEvent.keyDown(input(), { key: 'Enter' }); expect(route()).toBe('/profile');
    fireEvent.click(screen.getByRole('button', { name: 'Retry' })); await ready();
    expect(screen.getByRole('option', { name: /Even or Odd/ })).toBeTruthy();
    expect(input().value).toBe('even'); expect(mocks.loadLearningCatalog).toHaveBeenCalledTimes(2);
  });
  it('cannot navigate a locked result with a click or Enter', async () => {
    mocks.loadLearningCatalog.mockResolvedValue([{ ...taskEntry(), locked: true }]);
    mount(); query('even'); await ready(); const row = screen.getByRole('option', { name: /Even or Odd/ });
    expect(row.getAttribute('aria-disabled')).toBe('true');
    fireEvent.click(row); fireEvent.keyDown(input(), { key: 'ArrowDown' }); fireEvent.keyDown(input(), { key: 'Enter' });
    expect(route()).toBe('/profile'); expect(mocks.queryTutor).not.toHaveBeenCalled();
  });
  it.each([null, 'UNAUTHORIZED'])('does not load or expose results without Workspace authorization (%s)', async (identity) => {
    if (identity === null) mocks.user = null;
    else mocks.role = identity;
    mount(); expect(input().disabled).toBe(true);
    query('loop'); fireEvent.keyDown(input(), { key: 'Enter' });
    await act(async () => {});
    expect(screen.queryByRole('listbox')).toBeNull(); expect(mocks.loadLearningCatalog).not.toHaveBeenCalled();
    expect(mocks.getAssessmentItems).not.toHaveBeenCalled(); expect(mocks.searchCurriculum).not.toHaveBeenCalled();
    expect(route()).toBe('/profile');
  });
  it('the clear control removes the query and resets expanded results', async () => {
    mount(); query('loop'); await ready();
    fireEvent.click(screen.getByRole('button', { name: 'Clear search' }));
    expect(input().value).toBe(''); expect(input().getAttribute('aria-expanded')).toBe('false');
    expect(screen.queryByRole('listbox')).toBeNull();
  });
});

const mountApp = (start, controls = null) => render(
  <MemoryRouter initialEntries={[start]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
    <AppShell><Routes>
      <Route path="/profile" element={<Profile />} /><Route path="/dashboard" element={<Dashboard />} />
      <Route path="/workspace" element={<Workspace />} /><Route path="/assessment" element={<AssessmentPage />} />
    </Routes></AppShell>{controls}<Location />
  </MemoryRouter>,
);
describe('shared application header', () => {
  it.each(['/profile', '/dashboard', '/assessment'])('searches and opens the practice task from %s', async (start) => {
    mountApp(start);
    if (start === '/assessment') await waitFor(() => expect(mocks.getAssessmentItems).toHaveBeenCalledTimes(1));
    const assessmentCalls = mocks.getAssessmentItems.mock.calls.length;
    query(task.id); await ready(); fireEvent.click(screen.getByRole('option', { name: /Even or Odd/ }));
    await waitFor(() => expect(screen.getByLabelText('Code editor').getAttribute('data-problem')).toBe(task.id));
    expect(route()).toBe(taskEntry().destination);
    expect(screen.queryByRole('listbox')).toBeNull();
    expect(mocks.getAssessmentItems).toHaveBeenCalledTimes(assessmentCalls);
    expect(mocks.searchCurriculum).not.toHaveBeenCalled(); expect(mocks.queryTutor).not.toHaveBeenCalled();
  });
  it('updates an already-open Workspace task through its URL without erasing a tutor draft', async () => {
    mountApp('/workspace?problem=prob_c_loop_101');
    const draft = screen.getByRole('textbox', { name: /Ask the tutor/ });
    await waitFor(() => expect(draft.readOnly).toBe(false));
    fireEvent.change(draft, { target: { value: 'Please keep my unfinished tutor question.' } });
    query(task.id); await ready(); fireEvent.keyDown(input(), { key: 'Enter' });
    await waitFor(() => expect(screen.getByLabelText('Code editor').getAttribute('data-problem')).toBe(task.id));
    expect(route()).toBe(taskEntry().destination);
    expect(screen.getByLabelText('Code editor').value).toBe(task.starterCode);
    expect(screen.getByRole('textbox', { name: /Ask the tutor/ }).value).toBe('Please keep my unfinished tutor question.');
    expect(mocks.queryTutor).not.toHaveBeenCalled();
  });
  it('selecting the current task keeps edited code and the tutor question, including its request context', async () => {
    const current = NCTB_PROBLEMS[0];
    const editedCode = '#include <stdio.h>\nint main(void) { puts("Unfinished edit"); return 0; }';
    const question = 'Please review my unfinished code.';
    mocks.queryTutor.mockResolvedValue({ ai_status: 'live', provider: 'openai', model: 'gpt-5-mini', direct_answer: 'Test response' });
    mountApp('/workspace');
    const draft = screen.getByRole('textbox', { name: /Ask the tutor/ });
    await waitFor(() => expect(draft.readOnly).toBe(false));
    fireEvent.change(screen.getByLabelText('Code editor'), { target: { value: editedCode } });
    fireEvent.change(draft, { target: { value: question } });
    query(current.id); await ready(); fireEvent.keyDown(input(), { key: 'Enter' });
    await waitFor(() => expect(route()).toBe('/workspace?problem=' + current.id));
    expect(screen.getByLabelText('Code editor').value).toBe(editedCode);
    expect(screen.getByRole('textbox', { name: /Ask the tutor/ }).value).toBe(question);
    fireEvent.click(screen.getByRole('button', { name: 'Get Fix', exact: true }));
    await waitFor(() => expect(mocks.queryTutor).toHaveBeenCalledTimes(1));
    expect(mocks.queryTutor.mock.calls[0].slice(0, 3)).toEqual([question, editedCode, current.id]);
  });
  it('browser back to the initial Workspace restores its default task without erasing the tutor draft', async () => {
    mountApp('/workspace', <HistoryBack />);
    const question = 'Keep this unfinished question when I go back.';
    const draft = screen.getByRole('textbox', { name: /Ask the tutor/ });
    await waitFor(() => expect(draft.readOnly).toBe(false));
    fireEvent.change(draft, { target: { value: question } });
    query(task.id); await ready(); fireEvent.keyDown(input(), { key: 'Enter' });
    await waitFor(() => expect(screen.getByLabelText('Code editor').getAttribute('data-problem')).toBe(task.id));
    expect(route()).toBe(taskEntry().destination);
    fireEvent.click(screen.getByRole('button', { name: 'Go back', exact: true }));
    await waitFor(() => expect(screen.getByLabelText('Code editor').getAttribute('data-problem')).toBe(NCTB_PROBLEMS[0].id));
    expect(route()).toBe('/workspace');
    expect(screen.getByLabelText('Code editor').value).toBe(NCTB_PROBLEMS[0].starterCode);
    expect(screen.getByRole('textbox', { name: /Ask the tutor/ }).value).toBe(question);
    expect(mocks.queryTutor).not.toHaveBeenCalled();
  });
  it('keeps pre-test tutor restrictions enforced after choosing a practice task', async () => {
    mocks.getDashboard.mockResolvedValue({ ...dashboard(), tutor_availability: { available: false, exam_type: 'pre' } });
    mountApp('/workspace'); await screen.findByText('Tutor temporarily unavailable');
    query(task.id); await ready(); fireEvent.keyDown(input(), { key: 'Enter' });
    await waitFor(() => expect(screen.getByLabelText('Code editor').getAttribute('data-problem')).toBe(task.id));
    expect(screen.getByRole('button', { name: 'Get Fix', exact: true }).disabled).toBe(true);
    expect(screen.getByText('Tutor temporarily unavailable')).toBeTruthy();
    expect(mocks.queryTutor).not.toHaveBeenCalled(); expect(mocks.getAssessmentItems).not.toHaveBeenCalled();
  });
  it('supports narrow-screen pointer selection and existing sidebar navigation', async () => {
    const originalWidth = window.innerWidth;
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 360 });
    try {
      mountApp('/profile'); query('loop'); await ready();
      const row = screen.getByRole('option', { name: /Sum of First N/ });
      fireEvent.pointerDown(row, { pointerType: 'touch' }); fireEvent.click(row);
      await waitFor(() => expect(route()).toBe('/workspace?problem=prob_c_loop_101'));
      const dashboardLink = screen.getAllByRole('link').find((link) => link.getAttribute('href') === '/dashboard');
      fireEvent.click(dashboardLink);
      await waitFor(() => expect(route()).toBe('/dashboard'));
      expect(input()).toBeTruthy(); expect(screen.queryByRole('listbox')).toBeNull();
      expect(mocks.searchCurriculum).not.toHaveBeenCalled();
    } finally {
      Object.defineProperty(window, 'innerWidth', { configurable: true, value: originalWidth });
    }
  });
});
