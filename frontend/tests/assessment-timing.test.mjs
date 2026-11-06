import test from 'node:test';
import assert from 'node:assert/strict';
import { formatTimingDate, formatElapsedDays } from '../src/services/assessmentTiming.js';

test('calendar durations retain days and minutes, including zero and missing times', () => {
  assert.equal(formatElapsedDays(7.5), '7 দিন 12 ঘণ্টা 0 মিনিট');
  assert.equal(formatElapsedDays(0), '0 দিন 0 ঘণ্টা 0 মিনিট');
  assert.equal(formatElapsedDays(null), '—');
  assert.equal(formatElapsedDays(1 / 1440), '0 দিন 0 ঘণ্টা 1 মিনিট');
});

test('dates use Dhaka time and handle unavailable values', () => {
  assert.match(formatTimingDate('2026-07-01T18:10:11Z'), /02 Jul 2026.*00:10:11/);
  assert.equal(formatTimingDate(null), '—');
  assert.equal(formatTimingDate('invalid'), '—');
});
