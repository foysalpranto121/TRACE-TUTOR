import { StrictMode } from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { Workspace } from '../src/pages/Workspace';
import { assessmentChanged } from '../src/services/assessmentEvents';

const mocks = vi.hoisted(() => ({
  arm: 'ANSWER_ONLY',
  getDashboard: vi.fn(), queryTutor: vi.fn(), getCodeStatus: vi.fn(), logTelemetry: vi.fn(),
}));
vi.mock('../src/services/api', () => ({ apiService: mocks }));
vi.mock('../src/context/useAuth', () => ({ useAuth: () => ({ user: { id: 42 }, arm: mocks.arm, language: 'en' }) }));
vi.mock('../src/components/Editor/CodeEditor', () => ({ CodeEditor: () => <div>Code editor</div> }));
vi.mock('../src/components/ui/useCelebrate', () => ({ useCelebrate: () => ({ toast: vi.fn(), levelUp: vi.fn() }) }));
const dashboard = (available, exam_type = null) => ({ stats: {}, assessments: {}, problems: [], tutor_availability: { available, exam_type } });
const mount = (strict = false) => render(<MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>{strict ? <StrictMode><Workspace /></StrictMode> : <Workspace />}</MemoryRouter>);
const input = () => screen.getByRole('textbox', { name: /Ask the tutor/ });
const button = () => screen.getByRole('button', { name: mocks.arm === 'ANSWER_ONLY' ? 'Get Fix' : 'Ask', exact: true });
const ready = async () => waitFor(() => expect(input().readOnly).toBe(false));
const draft = () => fireEvent.change(input(), { target: { value: 'Why is my loop wrong?' } });
const deferred = () => { let resolve; const promise = new Promise((done) => { resolve = done; }); return { promise, resolve }; };

beforeEach(() => {
  mocks.arm = 'ANSWER_ONLY';
  mocks.getDashboard.mockReset().mockResolvedValue(dashboard(true));
  mocks.queryTutor.mockReset().mockResolvedValue({ direct_answer: 'Use the correct loop condition.' });
  mocks.getCodeStatus.mockResolvedValue({ ready: true, c: 'Clang' });
  mocks.logTelemetry.mockResolvedValue({});
});
afterEach(() => { cleanup(); vi.useRealTimers(); });

for (const arm of ['ANSWER_ONLY', 'REASONING_VISIBLE']) {
  describe(arm, () => {
    beforeEach(() => { mocks.arm = arm; });
    it('shows the pre-test restriction immediately and rejects even a forced form submission', async () => {
      mocks.getDashboard.mockResolvedValue(dashboard(false, 'pre'));
      mount();
      await screen.findByText('Tutor temporarily unavailable');
      expect(screen.getByText('Your pre-test is still in progress. Please submit your paper before using the AI Tutor.')).toBeTruthy();
      expect(button().disabled).toBe(true);
      expect(input().readOnly).toBe(true);
      fireEvent.submit(input().closest('form'));
      expect(mocks.queryTutor).not.toHaveBeenCalled();
      expect(screen.queryByText(/Generating direct|generating Gemini/)).toBeNull();
    });
    it('preserves the draft on a policy rejection and restores it after unlocking', async () => {
      mocks.queryTutor.mockRejectedValue(Object.assign(new Error('Paper in progress'), { body: { reason: 'paper_in_progress', exam_type: 'pre' } }));
      mount(); await ready(); draft(); fireEvent.click(button());
      await screen.findByText('Tutor temporarily unavailable');
      expect(input().value).toBe('Why is my loop wrong?');
      expect(button().disabled).toBe(true);
      await act(async () => { await assessmentChanged(Promise.resolve({ status: 'saved' })); });
      await ready();
      expect(input().value).toBe('Why is my loop wrong?');
      expect(button().disabled).toBe(false);
    });
    it('preserves the draft on network and server failures', async () => {
      mocks.queryTutor.mockRejectedValue(new Error('Network unavailable'));
      mount(); await ready(); draft(); fireEvent.click(button());
      await screen.findByText('Network unavailable');
      expect(input().value).toBe('Why is my loop wrong?');
      expect(button().disabled).toBe(false);
    });
    it('clears the draft only once a normal request succeeds', async () => {
      const request = deferred(); mocks.queryTutor.mockReturnValue(request.promise);
      mount(); await ready(); draft(); fireEvent.click(button());
      await waitFor(() => expect(mocks.queryTutor).toHaveBeenCalledTimes(1));
      expect(input().value).toBe('Why is my loop wrong?');
      expect(button().disabled).toBe(true);
      await act(async () => { request.resolve({ direct_answer: 'Accepted' }); });
      await waitFor(() => expect(input().value).toBe(''));
    });
  });
}
it('restores the server restriction after navigation remount and a fresh page mount', async () => {
  mocks.getDashboard.mockResolvedValue(dashboard(false, 'pre'));
  for (let navigation = 0; navigation < 3; navigation++) {
    const view = mount(); await screen.findByText('Tutor temporarily unavailable');
    expect(button().disabled).toBe(true); view.unmount();
  }
  expect(mocks.getDashboard).toHaveBeenCalledTimes(3);
});
it('coalesces the initial dashboard/progress check under StrictMode', async () => {
  mount(true); await ready(); expect(mocks.getDashboard).toHaveBeenCalledTimes(1);
});
it('blocks submission while initial availability is loading', async () => {
  const check = deferred(); mocks.getDashboard.mockReturnValue(check.promise);
  mount(); expect(screen.getByText('Checking tutor availability…')).toBeTruthy();
  fireEvent.submit(input().closest('form'));
  expect(mocks.queryTutor).not.toHaveBeenCalled(); expect(button().disabled).toBe(true);
  await act(async () => { check.resolve(dashboard(true)); }); await ready();
});
it('fails closed on availability errors and retries without losing a draft', async () => {
  mount(); await ready(); draft();
  mocks.getDashboard.mockRejectedValueOnce(new Error('Status offline'));
  fireEvent.click(button());
  await screen.findByText('Could not verify tutor availability');
  expect(input().value).toBe('Why is my loop wrong?');
  expect(button().disabled).toBe(true); expect(mocks.queryTutor).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Retry' })); await ready();
  expect(input().value).toBe('Why is my loop wrong?');
});
it('rechecks before generating and prevents a request if another device opened a pre-test', async () => {
  mount(); await ready(); draft();
  mocks.getDashboard.mockResolvedValue(dashboard(false, 'pre'));
  fireEvent.click(button()); await screen.findByText('Tutor temporarily unavailable');
  expect(mocks.queryTutor).not.toHaveBeenCalled(); expect(input().value).toBe('Why is my loop wrong?');
});
it('refreshes after submission, cross-tab changes and window focus', async () => {
  mocks.getDashboard.mockResolvedValue(dashboard(false, 'pre'));
  mount(); await screen.findByText('Tutor temporarily unavailable');
  mocks.getDashboard.mockResolvedValue(dashboard(true));
  await act(async () => { await assessmentChanged(Promise.resolve({ status: 'saved' })); });
  await ready();
  mocks.getDashboard.mockResolvedValue(dashboard(false, 'withdrawal'));
  fireEvent(window, new StorageEvent('storage', { key: 'trace:assessment-changed' }));
  await screen.findByText(/Your withdrawal task is still in progress/);
  mocks.getDashboard.mockResolvedValue(dashboard(true)); fireEvent.focus(window); await ready();
});
it('refreshes an open Workspace periodically for changes on other devices', async () => {
  mount(); await ready(); mocks.getDashboard.mockResolvedValue(dashboard(false, 'pre'));
  vi.useFakeTimers();
  // Existing interval was created using real timers; remount with fake timers.
  cleanup(); mount();
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
  mocks.getDashboard.mockResolvedValue(dashboard(true));
  await act(async () => { await vi.advanceTimersByTimeAsync(30000); });
  expect(input().readOnly).toBe(false);
});
it('shows the notice and disabled mobile controls in the same responsive panel', async () => {
  Object.defineProperty(window, 'innerWidth', { value: 375, configurable: true });
  mocks.getDashboard.mockResolvedValue(dashboard(false, 'pre'));
  const view = mount(); await screen.findByText('Tutor temporarily unavailable');
  expect(view.container.querySelector('.grid-cols-1')).toBeTruthy();
  expect(input().className).toContain('min-w-0');
  expect(button().disabled).toBe(true);
  expect(screen.getByRole('status').className).toContain('shrink-0');
});

it('fails closed when the initial availability request fails', async () => {
  mocks.getDashboard.mockRejectedValueOnce(new Error('Offline'));
  mount(); await screen.findByText('Could not verify tutor availability');
  expect(button().disabled).toBe(true);
  fireEvent.submit(input().closest('form'));
  expect(mocks.queryTutor).not.toHaveBeenCalled();
});
it('keeps the existing restriction visible during a status refresh', async () => {
  mocks.getDashboard.mockResolvedValue(dashboard(false, 'pre'));
  mount(); await screen.findByText('Tutor temporarily unavailable');
  const check = deferred(); mocks.getDashboard.mockReturnValue(check.promise);
  fireEvent.click(screen.getByRole('button', { name: 'Refresh status' }));
  expect(screen.getByText('Tutor temporarily unavailable')).toBeTruthy();
  expect(button().disabled).toBe(true);
  await act(async () => { check.resolve(dashboard(false, 'pre')); });
});
it('keeps a draft when availability changes and when the tutor mode switches', async () => {
  const view = mount(); await ready(); draft();
  mocks.arm = 'REASONING_VISIBLE';
  view.rerender(<MemoryRouter><Workspace /></MemoryRouter>);
  expect(input().value).toBe('Why is my loop wrong?');
  mocks.getDashboard.mockResolvedValue(dashboard(false, 'pre'));
  fireEvent(window, new Event('trace:assessment-changed'));
  await screen.findByText('Tutor temporarily unavailable');
  expect(input().value).toBe('Why is my loop wrong?');
});

it('does not flash a checking notice or disrupt the draft during focus refresh', async () => {
  mount(); await ready(); draft();
  const check = deferred(); mocks.getDashboard.mockReturnValue(check.promise);
  fireEvent.focus(window);
  expect(screen.queryByText('Checking tutor availability…')).toBeNull();
  expect(input().value).toBe('Why is my loop wrong?'); expect(input().readOnly).toBe(false);
  expect(button().disabled).toBe(false);
  await act(async () => { check.resolve(dashboard(true)); });
  expect(screen.queryByText('Checking tutor availability…')).toBeNull();
});
it('does not flash checking notices on repeated periodic refreshes after submission', async () => {
  vi.useFakeTimers(); mount();
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
  draft();
  for (let interval = 0; interval < 3; interval++) {
    const check = deferred(); mocks.getDashboard.mockReturnValueOnce(check.promise);
    await act(async () => { await vi.advanceTimersByTimeAsync(30000); });
    expect(screen.queryByText('Checking tutor availability…')).toBeNull();
    expect(input().readOnly).toBe(false); expect(input().value).toBe('Why is my loop wrong?');
    await act(async () => { check.resolve(dashboard(true)); });
    expect(screen.queryByText('Checking tutor availability…')).toBeNull();
  }
});
