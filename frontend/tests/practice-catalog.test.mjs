import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { NCTB_PROBLEMS } from '../src/data/problems.js';

const catalog = JSON.parse(readFileSync(new URL('../../backend/tutor/practice_tasks.json', import.meta.url), 'utf8'));

test('every public practice task has matching authoritative checks and an incomplete starter', () => {
  assert.deepEqual(Object.keys(catalog).sort(), NCTB_PROBLEMS.map((p) => p.id).sort());
  for (const problem of NCTB_PROBLEMS) {
    const task = catalog[problem.id];
    assert.equal(task.language, problem.lang);
    assert.match(problem.starterCode, /TODO:/);
    if (problem.lang === 'html') {
      assert.deepEqual(task.test_cases, problem.html_checks);
    } else {
      for (const sample of problem.sample_cases) assert.ok(task.test_cases.some((tc) => tc.input === sample.input && tc.output === sample.output));
      assert.ok(task.test_cases.length > problem.sample_cases.length);
    }
  }
});
