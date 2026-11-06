import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const source = readFileSync(new URL('../src/pages/AssessmentPage.jsx', import.meta.url), 'utf8');
const effect = source.split('// Grading completes after the initial items response.')[1]
  .match(/useEffect\(\(\) => \{([\s\S]*?)\n {2}\}, \[examType, isSubmitted, gradingState, phaseRefreshAttempt\]\);/)[1];
const run = new Function('apiService', 'examType', 'isSubmitted', 'gradingState', 'setPhaseRefreshError', 'setAvailableExams', effect);
const tick = () => new Promise((resolve) => setImmediate(resolve));

test('completed grading unlocks transfer from server response without clearing results', async () => {
  let available = ['pre', 'post'];
  let calls = 0;
  run({ getAssessmentItems: async (type) => {
    assert.equal(type, 'post'); calls++;
    return { available: ['pre', 'post', 'transfer'] };
  } }, 'post', true, 'graded', () => {}, (value) => { available = value; });
  await tick();
  assert.equal(calls, 1);
  assert.deepEqual(available, ['pre', 'post', 'transfer']);
});

test('pending and failed grading do not unlock a later phase', () => {
  for (const status of ['pending', 'grading', 'failed']) {
    run({ getAssessmentItems: () => { assert.fail('must not refresh'); } }, 'post', true, status, () => {}, () => {});
  }
});

test('a response from a previous phase is ignored after cleanup', async () => {
  let resolve;
  const cleanup = run({ getAssessmentItems: () => new Promise((done) => { resolve = done; }) },
    'post', true, 'graded', () => {}, () => assert.fail('stale response changed availability'));
  cleanup();
  resolve({ available: ['pre', 'post', 'transfer'] });
  await tick();
});

test('refresh failure preserves availability and reports a retryable error', async () => {
  let error;
  run({ getAssessmentItems: async () => { throw new Error('offline'); } }, 'post', true, 'graded',
    (value) => { error = value; }, () => assert.fail('must preserve existing availability'));
  await tick();
  assert.match(error, /Your result is saved/);
});
