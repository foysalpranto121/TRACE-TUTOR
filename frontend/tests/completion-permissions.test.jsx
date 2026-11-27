import { useEffect } from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AuthProvider } from '../src/context/AuthContext';
import { useAuth } from '../src/context/useAuth';
import { AppShell } from '../src/components/Layout/AppShell';
import { AssessmentPage } from '../src/pages/AssessmentPage';
import { loadSession, saveSession } from '../src/services/session';

const mocks = vi.hoisted(() => ({
  me: vi.fn(), getDashboard: vi.fn(), logTelemetry: vi.fn(), logout: vi.fn(), login: vi.fn(),
  updateProfile: vi.fn(), getAssessmentItems: vi.fn(), getSubmission: vi.fn(), retakeAssessment: vi.fn(),
  observedPermissions: [],
}));
vi.mock('../src/services/api', () => ({ apiService: mocks }));
vi.mock('../src/context/useTheme', () => ({ useTheme: () => ({ isDark: false, toggleTheme: vi.fn() }) }));
vi.mock('../src/components/Layout/HeaderSearch', () => ({ HeaderSearch: () => <div>Search</div> }));

const TOKEN = 'a'.repeat(40);
const student = (extra = {}) => ({ id: 1, username: 'learner', full_name: 'Learner', role: 'STUDENT',
  arm: 'REASONING_VISIBLE', language: 'en', arm_self_select: false,
  arm_switch_reason: 'after_protocol', arm_switch_policy: 'after_protocol', ...extra });
const completed = () => student({ arm_self_select: true, arm_switch_reason: 'completed' });
const deferred = () => {
  let resolve;
  let reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
};
const assessmentChanged = () => window.dispatchEvent(new Event('trace:assessment-changed'));
const account = () => JSON.parse(screen.getByTestId('account').textContent);
const switchButton = () => screen.queryByRole('button', { name: /Reasoning-Visible\s+switch/ });

function AccountProbe() {
  const auth = useAuth();
  useEffect(() => { mocks.observedPermissions.push(auth.user?.arm_self_select); }, [auth.user?.arm_self_select]);
  return <>
    <output data-testid="account">{JSON.stringify(auth.user)}</output>
    <output data-testid="ready">{String(auth.ready)}</output>
    <button onClick={auth.logout}>Probe log out</button>
    <button onClick={() => auth.updateProfile({ full_name: 'Updated name', preferred_language: 'bn' })}>Edit profile</button>
    <button onClick={() => auth.login('other', 'password')}>Login other account</button>
  </>;
}

function mount(children = <AccountProbe />) {
  return render(<MemoryRouter initialEntries={['/assessment']} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
    <AuthProvider><AppShell>{children}</AppShell></AuthProvider>
  </MemoryRouter>);
}

beforeEach(() => {
  localStorage.clear(); sessionStorage.clear();
  Object.values(mocks).forEach((mock) => { if (typeof mock?.mockReset === 'function') mock.mockReset(); });
  mocks.observedPermissions = [];
  saveSession(student(), TOKEN);
  mocks.me.mockResolvedValue(student());
  mocks.getDashboard.mockResolvedValue({ stats: {}, assessments: {}, problems: [] });
  mocks.logTelemetry.mockResolvedValue({});
  mocks.logout.mockResolvedValue({});
});
afterEach(() => { cleanup(); localStorage.clear(); sessionStorage.clear(); });

it('unlocks the mode switch after the server confirms all papers, without logging in again', async () => {
  mount();
  await waitFor(() => expect(screen.getByTestId('ready').textContent).toBe('true'));
  expect(screen.getByText('after tests')).toBeTruthy();
  mocks.me.mockResolvedValue(completed());
  act(assessmentChanged);
  await waitFor(() => expect(switchButton()).toBeTruthy());
  expect(screen.queryByText('after tests')).toBeNull();
  expect(loadSession().user.arm_self_select).toBe(true);
  expect(account().arm_switch_reason).toBe('completed');
});

it('keeps unfinished participants locked and explains that this is a mode-switch lock', async () => {
  mount();
  await waitFor(() => expect(screen.getByTestId('ready').textContent).toBe('true'));
  act(assessmentChanged);
  await waitFor(() => expect(mocks.me).toHaveBeenCalledTimes(2));
  expect(screen.getByText('after tests')).toBeTruthy();
  expect(switchButton()).toBeNull();
  expect(screen.getByTitle(/This lock does not disable your assigned AI tutor/)).toBeTruthy();
});

it.each(['storage', 'focus', 'visible'])('refreshes permissions after %s signals', async (signal) => {
  mount();
  await waitFor(() => expect(screen.getByTestId('ready').textContent).toBe('true'));
  mocks.me.mockResolvedValue(completed());
  act(() => {
    if (signal === 'storage') window.dispatchEvent(new StorageEvent('storage', { key: 'trace:assessment-changed' }));
    else if (signal === 'focus') window.dispatchEvent(new Event('focus'));
    else document.dispatchEvent(new Event('visibilitychange'));
  });
  await waitFor(() => expect(switchButton()).toBeTruthy());
});

it('coalesces overlapping signals and ignores a permission response invalidated by a newer assessment', async () => {
  mount();
  await waitFor(() => expect(screen.getByTestId('ready').textContent).toBe('true'));
  const pending = deferred();
  mocks.me.mockReturnValueOnce(pending.promise).mockResolvedValue(student());
  act(assessmentChanged);
  await waitFor(() => expect(mocks.me).toHaveBeenCalledTimes(2));
  act(() => {
    assessmentChanged();
    window.dispatchEvent(new StorageEvent('storage', { key: 'trace:assessment-changed' }));
    window.dispatchEvent(new Event('focus'));
  });
  expect(mocks.me).toHaveBeenCalledTimes(2);
  await act(async () => pending.resolve(completed()));
  await waitFor(() => expect(mocks.me).toHaveBeenCalledTimes(3));
  expect(account().arm_self_select).toBe(false);
  expect(mocks.observedPermissions).not.toContain(true);
});

it.each(['initial', 'background'])('does not resurrect a logged-out user after a pending %s profile response', async (stage) => {
  const pending = deferred();
  if (stage === 'initial') mocks.me.mockReturnValueOnce(pending.promise);
  mount();
  if (stage === 'background') {
    await waitFor(() => expect(screen.getByTestId('ready').textContent).toBe('true'));
    mocks.me.mockReturnValueOnce(pending.promise);
    act(assessmentChanged);
    await waitFor(() => expect(mocks.me).toHaveBeenCalledTimes(2));
  } else await waitFor(() => expect(mocks.me).toHaveBeenCalledTimes(1));
  fireEvent.click(screen.getByRole('button', { name: 'Probe log out' }));
  await act(async () => pending.resolve(completed()));
  expect(account()).toBeNull();
  expect(loadSession().user).toBeNull();
  expect(screen.getByTestId('ready').textContent).toBe('true');
});

it('does not apply an old student response after another account logs in', async () => {
  const pending = deferred();
  mocks.me.mockReturnValueOnce(pending.promise);
  mocks.login.mockResolvedValue({ token: 'b'.repeat(40), user: {
    ...completed(), id: 2, username: 'teacher', full_name: 'Teacher', role: 'EXPERT_TEACHER', arm_switch_reason: 'staff',
  } });
  mount();
  await waitFor(() => expect(mocks.me).toHaveBeenCalledTimes(1));
  fireEvent.click(screen.getByRole('button', { name: 'Login other account' }));
  await waitFor(() => expect(account().id).toBe(2));
  await act(async () => pending.resolve(student()));
  expect(account().role).toBe('EXPERT_TEACHER');
  expect(loadSession().user.id).toBe(2);
});

it('never overwrites profile edits with an older or background eligibility response', async () => {
  mount();
  await waitFor(() => expect(screen.getByTestId('ready').textContent).toBe('true'));
  const pending = deferred();
  mocks.me.mockReturnValueOnce(pending.promise);
  act(assessmentChanged);
  await waitFor(() => expect(mocks.me).toHaveBeenCalledTimes(2));
  mocks.updateProfile.mockResolvedValue(student({ full_name: 'Updated name', language: 'bn' }));
  fireEvent.click(screen.getByRole('button', { name: 'Edit profile' }));
  await waitFor(() => expect(account().full_name).toBe('Updated name'));
  await act(async () => pending.resolve(completed()));
  expect(account().full_name).toBe('Updated name');
  expect(account().language).toBe('bn');
  mocks.me.mockResolvedValue(completed());
  act(() => window.dispatchEvent(new Event('focus')));
  await waitFor(() => expect(account().arm_self_select).toBe(true));
  expect(account().full_name).toBe('Updated name');
  expect(account().language).toBe('bn');
});

it('preserves the known lock when a refresh fails', async () => {
  mount();
  await waitFor(() => expect(screen.getByTestId('ready').textContent).toBe('true'));
  mocks.me.mockRejectedValueOnce(new Error('offline'));
  act(assessmentChanged);
  await waitFor(() => expect(mocks.me).toHaveBeenCalledTimes(2));
  expect(account().arm_self_select).toBe(false);
  expect(loadSession().user.arm_self_select).toBe(false);
});

it('removes historical no-AI warnings from completed results, then restores the withdrawal warning on retake', async () => {
  mocks.me.mockResolvedValue(completed());
  const paper = { id: 'html-pre', type: 'concept_mcq', title: 'HTML concept', chapter: 'Chapter 4',
    question: 'Which element describes a paragraph?', options: [{ id: 'a', text: 'Paragraph' }] };
  mocks.getAssessmentItems.mockImplementation(async (type) => ({ available: ['pre', 'post', 'transfer', 'withdrawal'],
    items: [paper], sitting: { status: 'completed', submission_id: type === 'withdrawal' ? 44 : 11 } }));
  mocks.getSubmission.mockImplementation(async (id) => ({ submission_id: id, grading_status: 'graded',
    score_pct: 100, correct: 1, total: 1, results: [] }));
  mocks.retakeAssessment.mockResolvedValue({ available: ['pre', 'post', 'transfer', 'withdrawal'],
    items: [paper], sitting: { status: 'open', submission_id: null } });
  mount(<AssessmentPage />);
  await screen.findByText('Assessment Complete!');
  expect(screen.queryByText('Pre-Test Baseline Assessment:')).toBeNull();
  expect(screen.getByRole('link', { name: 'Open AI Workspace' }).getAttribute('href')).toBe('/workspace');
  fireEvent.click(screen.getByRole('button', { name: 'Withdrawal Task (No AI)' }));
  await waitFor(() => expect(mocks.getSubmission).toHaveBeenCalledWith(44));
  await screen.findByText('Assessment Complete!');
  expect(screen.queryByText('AI Tutor Withdrawal Task:')).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Retake Assessment' }));
  await screen.findByText('AI Tutor Withdrawal Task:');
  expect(screen.queryByText('Assessment Complete!')).toBeNull();
  expect(screen.queryByRole('link', { name: 'Open AI Workspace' })).toBeNull();
});

it('continues to show the no-AI warning for a genuinely unfinished pre-test', async () => {
  mocks.getAssessmentItems.mockResolvedValue({ available: ['pre'], items: [{ id: 'pre-open', type: 'concept_mcq',
    title: 'Active pre-test', question: 'Active question', options: [] }], sitting: { status: 'open' } });
  mount(<AssessmentPage />);
  await screen.findByText('Pre-Test Baseline Assessment:');
  expect(screen.queryByRole('link', { name: 'Open AI Workspace' })).toBeNull();
});

it('does not briefly reopen a completed paper while its recorded result is loading', async () => {
  const pending = deferred();
  mocks.getAssessmentItems.mockResolvedValue({ available: ['pre'],
    items: [{ id: 'submitted-pre', type: 'concept_mcq', title: 'Submitted pre-test', question: 'Recorded question', options: [] }],
    sitting: { status: 'completed', submission_id: 11 } });
  mocks.getSubmission.mockReturnValue(pending.promise);
  mount(<AssessmentPage />);
  await waitFor(() => expect(mocks.getSubmission).toHaveBeenCalledWith(11));
  expect(screen.queryByTestId('question-card')).toBeNull();
  expect(screen.queryByText('Pre-Test Baseline Assessment:')).toBeNull();
  await act(async () => pending.resolve({ submission_id: 11, grading_status: 'graded', score_pct: 100,
    correct: 1, total: 1, results: [] }));
  await screen.findByText('Assessment Complete!');
});
