import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { CodeEditor } from '../src/components/Editor/CodeEditor';
import { NCTB_PROBLEMS } from '../src/data/problems';

const mocks = vi.hoisted(() => ({ runCode: vi.fn(), getCodeStatus: vi.fn(), logTelemetry: vi.fn() }));
vi.mock('../src/services/api', () => ({ apiService: mocks }));
vi.mock('../src/context/useAuth', () => ({ useAuth: () => ({ language: 'en' }) }));
vi.mock('../src/context/useTheme', () => ({ useTheme: () => ({ isDark: false }) }));
vi.mock('@monaco-editor/react', () => ({ default: ({ value }) => <textarea aria-label="Practice source" value={value} readOnly /> }));

beforeEach(() => {
  mocks.runCode.mockReset();
  mocks.getCodeStatus.mockResolvedValue({ ready: true, c: 'Test compiler' });
  mocks.logTelemetry.mockReset().mockResolvedValue({ logged: true });
});
afterEach(cleanup);

it('runs the selected C task through the server and forwards its recorded result', async () => {
  const problem = NCTB_PROBLEMS[0];
  const onCompileResult = vi.fn();
  mocks.runCode.mockResolvedValue({ status: 'SUCCESS', practice_metric_version: 2, passed_count: 4, test_results: [] });
  render(<CodeEditor initialCode={problem.starterCode} language="c" sampleCases={problem.sample_cases} activeProblem={problem} onCompileResult={onCompileResult} />);
  expect(screen.getByRole('textbox', { name: 'Practice source' }).value).toContain('TODO:');
  fireEvent.click(screen.getByRole('button', { name: 'Run Code' }));
  await waitFor(() => expect(onCompileResult).toHaveBeenCalledWith(expect.objectContaining({ status: 'SUCCESS', practice_metric_version: 2 })));
  expect(mocks.runCode).toHaveBeenCalledWith('c', problem.starterCode, problem.sample_cases, 'run', problem.id);
  expect(mocks.logTelemetry).not.toHaveBeenCalledWith('CODE_RESULT', expect.anything());
});

it('records an HTML practice run through the same authoritative endpoint', async () => {
  const problem = NCTB_PROBLEMS.find((p) => p.lang === 'html');
  const onCompileResult = vi.fn();
  mocks.runCode.mockResolvedValue({ status: 'WRONG_ANSWER', practice_metric_version: 2, passed_count: 0, test_results: [] });
  render(<CodeEditor initialCode={problem.starterCode} language="html" htmlChecks={problem.html_checks} activeProblem={problem} onCompileResult={onCompileResult} />);
  fireEvent.click(screen.getByRole('button', { name: 'Render HTML' }));
  await waitFor(() => expect(onCompileResult).toHaveBeenCalledWith(expect.objectContaining({ status: 'WRONG_ANSWER' })));
  expect(mocks.runCode).toHaveBeenCalledWith('html', problem.starterCode, problem.html_checks, 'run', problem.id);
  expect(mocks.logTelemetry).not.toHaveBeenCalledWith('CODE_RESULT', expect.anything());
});

it('shows an HTML preview without awarding credit when validation is unavailable', async () => {
  const problem = NCTB_PROBLEMS.find((p) => p.lang === 'html');
  const onCompileResult = vi.fn();
  mocks.runCode.mockRejectedValue(new Error('Offline'));
  render(<CodeEditor initialCode={problem.starterCode} language="html" activeProblem={problem} onCompileResult={onCompileResult} />);
  fireEvent.click(screen.getByRole('button', { name: 'Render HTML' }));
  await screen.findByTitle('HTML Preview Sandbox');
  expect(onCompileResult).not.toHaveBeenCalled();
  expect(mocks.logTelemetry).not.toHaveBeenCalledWith('CODE_RESULT', expect.anything());
});
