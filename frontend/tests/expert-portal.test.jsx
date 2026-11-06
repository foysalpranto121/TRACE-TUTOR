import { beforeEach, afterEach, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor, act } from '@testing-library/react';
import { ExpertPortal } from '../src/pages/ExpertPortal';
import { formatScore } from '../src/services/score';

const mocks = vi.hoisted(() => ({ language: 'en', user: { id: 42 }, getExpertQueue: vi.fn(), getStudentSubmissions: vi.fn(), submitExpertRating: vi.fn(), gradeSubmission: vi.fn() }));
vi.mock('../src/services/api', () => ({ apiService: mocks }));
vi.mock('../src/context/useAuth', () => ({ useAuth: () => ({ user: mocks.user, role: 'EXPERT_TEACHER', language: mocks.language }) }));
const criteria = ['Curriculum alignment', 'Technical accuracy', 'Language clarity', 'Grade 11-12 difficulty', 'Defensible answerability'];
const scores = (value) => Object.fromEntries(['alignment', 'accuracy', 'clarity', 'difficulty', 'answerability'].map((key) => [key, value]));
const item = (id, mine = null) => ({ id, title: 'Item ' + id, question_text: 'Question ' + id, exam_type: 'pre', ratings_count: mine ? 1 : 0, my_rating: mine, rating_revision: mine ? 'rating-old' : null });
const queue = (items = [item('one'), item('two')]) => ({ items_to_review: items, cvi_stats: { total_items: 2, rated_items: 0, expert_count: 0, ratings_count: 0 } });
const submission = (score = null, status = 'graded') => ({ id: 1, student_label: 'Disposable TT', participant_code: 'TT-QA', exam_type: 'pre', code_answers: [], score_pct: score, grading_status: status, max_marks: 100, grade_revision: null });
const mount = () => render(<ExpertPortal />);
const ready = () => screen.findByText('Item one');
const comment = () => screen.getByRole('textbox', { name: /Expert comments/ });
const next = () => fireEvent.click(screen.getByRole('button', { name: 'Next' }));
const previous = () => fireEvent.click(screen.getByRole('button', { name: 'Previous' }));
const rate = (value) => criteria.forEach((name) => fireEvent.click(screen.getByRole('button', { name: name + ': ' + value + ' of 4' })));
const selected = (value) => criteria.forEach((name) => expect(screen.getByRole('button', { name: name + ': ' + value + ' of 4' }).getAttribute('aria-pressed')).toBe('true'));
const marking = async () => { await ready(); fireEvent.click(screen.getByRole('button', { name: /Code grading/ })); return screen.findByRole('button', { name: /Save marks/ }); };
const deferred = () => { let resolve; const promise = new Promise((done) => { resolve = done; }); return { promise, resolve }; };
it('shows opening, submission, elapsed days and incomplete study timing without invented dates', async () => {
  mocks.getStudentSubmissions.mockResolvedValue({ submissions: [{ ...submission(47), timing: {
    opened_at: '2026-07-01T03:00:00Z', submitted_at: '2026-07-02T15:00:00Z',
    paper_elapsed_days: 1.5, study_started_at: '2026-07-01T03:00:00Z', study_completed_at: null,
    study_elapsed_days: null, window_start: '2026-07-01T00:00:00+06:00', window_end: '2026-10-20T23:59:59+06:00',
  } }] });
  mount(); await marking();
  expect(screen.getByText('Dates & time')).toBeTruthy();
  expect(screen.getByText('1 days 12 hours 0 minutes')).toBeTruthy();
  expect(screen.getByText('Not yet completed')).toBeTruthy();
  expect(screen.getAllByText(/01 Jul 2026.*09:00:00/, { selector: 'dd' })).toHaveLength(2);
});
beforeEach(() => {
  mocks.user = { id: 42 };
  mocks.language = 'en';
  mocks.getExpertQueue.mockReset().mockResolvedValue(queue());
  mocks.getStudentSubmissions.mockReset().mockResolvedValue({ submissions: [submission()] });
  mocks.submitExpertRating.mockReset().mockResolvedValue({ item_id: 'one', rated: true, rating_revision: 'rating-new' });
  mocks.gradeSubmission.mockReset().mockResolvedValue({ submission_id: 1, assigned_marks: 70, max_marks: 100, grade_revision: 'grade-new' });
});
afterEach(cleanup);

it('preserves five ratings and comments independently across Next and Previous, without submitting', async () => {
  mount(); await ready(); rate(4); fireEvent.change(comment(), { target: { value: 'First research draft' } });
  next(); await screen.findByText('Item two'); rate(2); fireEvent.change(comment(), { target: { value: 'Second research draft' } });
  previous(); selected(4); expect(comment().value).toBe('First research draft');
  fireEvent.click(screen.getByRole('button', { name: 'Technical accuracy: 3 of 4' }));
  next(); selected(2); expect(comment().value).toBe('Second research draft');
  previous(); expect(screen.getByRole('button', { name: 'Technical accuracy: 3 of 4' }).getAttribute('aria-pressed')).toBe('true');
  expect(screen.getByRole('status').textContent).toContain('Unsaved draft');
  expect(mocks.submitExpertRating).not.toHaveBeenCalled();
});
it('requires all five deliberate scores and clears only the explicitly submitted item draft', async () => {
  mount(); await ready(); const submit = () => screen.getByRole('button', { name: /Submit/ });
  expect(submit().disabled).toBe(true);
  criteria.slice(0, 4).forEach((name) => fireEvent.click(screen.getByRole('button', { name: name + ': 4 of 4' })));
  expect(submit().disabled).toBe(true); fireEvent.click(screen.getByRole('button', { name: criteria[4] + ': 4 of 4' }));
  fireEvent.change(comment(), { target: { value: 'Explicit final feedback' } });
  next(); rate(2); previous();
  mocks.getExpertQueue.mockResolvedValue(queue([item('one', { ...scores(4), feedback: 'Explicit final feedback' }), item('two')]));
  fireEvent.click(submit()); await waitFor(() => expect(mocks.submitExpertRating).toHaveBeenCalledWith('one', scores(4), 'Explicit final feedback', null));
  await screen.findByText('Item two'); selected(2); previous(); selected(4); expect(comment().value).toBe('Explicit final feedback');
  expect(screen.queryByRole('status')).toBeNull();
});
it('retains drafts after a failed submission and prevents editing/navigation during a pending write', async () => {
  const pending = deferred(); mocks.submitExpertRating.mockReturnValue(pending.promise);
  mount(); await ready(); rate(3); fireEvent.change(comment(), { target: { value: 'Keep me' } });
  fireEvent.click(screen.getByRole('button', { name: /Submit/ }));
  expect(screen.getByRole('button', { name: 'Next' }).disabled).toBe(true); expect(comment().disabled).toBe(true);
  await act(async () => pending.resolve(Promise.reject(new Error('Network failed'))));
  await screen.findByText(/Network failed/); selected(3); expect(comment().value).toBe('Keep me');
});
it('keeps submitted ratings separate from memory-only drafts after remount or an account change', async () => {
  mocks.getExpertQueue.mockResolvedValue(queue([item('one', { ...scores(3), feedback: 'Stored comment' }), item('two')]));
  const view = mount(); await ready(); selected(3); fireEvent.change(comment(), { target: { value: 'Unsaved private comment' } });
  view.unmount(); const reopened = mount(); await ready(); selected(3); expect(comment().value).toBe('Stored comment');
  fireEvent.change(comment(), { target: { value: 'Account 42 only' } });
  mocks.user = { id: 99 }; mocks.getExpertQueue.mockResolvedValue(queue()); reopened.rerender(<ExpertPortal />); await ready();
  expect(comment().value).toBe(''); expect(screen.queryByRole('status')).toBeNull();
});
it('keeps a conflicting draft until the expert explicitly reloads the latest rating', async () => {
  mocks.submitExpertRating.mockRejectedValue(Object.assign(new Error('Changed in another session'), { status: 409 }));
  mount(); await ready(); rate(2); fireEvent.change(comment(), { target: { value: 'Do not discard silently' } });
  fireEvent.click(screen.getByRole('button', { name: /Submit/ })); await screen.findByText(/Changed in another session/);
  expect(comment().value).toBe('Do not discard silently');
  mocks.getExpertQueue.mockResolvedValue(queue([item('one', { ...scores(4), feedback: 'Latest server comment' }), item('two')]));
  fireEvent.click(screen.getByRole('button', { name: 'Discard draft and load latest rating' }));
  await waitFor(() => expect(comment().value).toBe('Latest server comment')); selected(4);
});
it('refresh has an accessible name and fetches changed records, with a disabled loading state', async () => {
  mount(); await marking(); const button = screen.getByRole('button', { name: 'Refresh submissions' });
  button.focus(); expect(document.activeElement).toBe(button);
  const pending = deferred(); mocks.getStudentSubmissions.mockReturnValue(pending.promise); fireEvent.click(button);
  expect(button.disabled).toBe(true); expect(button.getAttribute('aria-busy')).toBe('true');
  await act(async () => pending.resolve({ submissions: [{ ...submission(85), id: 2, student_label: 'New disposable record' }] }));
  await screen.findAllByText('New disposable record'); expect(mocks.getStudentSubmissions).toHaveBeenCalledTimes(2);
  expect(screen.getAllByText(/85%/)).toHaveLength(2); expect(button.disabled).toBe(false);
});
it.each([[null, 'graded', 'Score unavailable'], [undefined, 'graded', 'Score unavailable'], [0, 'graded', '0%'], [85, 'graded', '85%'], ['bad', 'graded', 'Score unavailable'], [null, 'pending', 'Not graded'], [null, 'grading', 'Grading…']])('formats %s consistently in the list and detail card', async (value, status, expected) => {
  mocks.getStudentSubmissions.mockResolvedValue({ submissions: [submission(value, status)] }); mount(); await marking();
  expect(screen.getAllByText((_, element) => element.children.length === 0 && element.textContent.includes(expected))).toHaveLength(2);
  expect(document.body.textContent).not.toMatch(/null%|undefined%/);
});
it.each([NaN, Infinity, -1, 101, '85', true, {}, []])('rejects unexpected score formatting: %s', (value) => expect(formatScore(value)).toBe('Score unavailable'));
it.each(['', '-1', '101', '1.5'])('blocks invalid expert marks %s without an API write', async (value) => {
  mount(); await marking(); fireEvent.change(screen.getByRole('spinbutton', { name: /Assigned marks/ }), { target: { value } });
  fireEvent.click(screen.getByRole('button', { name: /Save marks/ })); await screen.findByText(/enter a mark/);
  expect(mocks.gradeSubmission).not.toHaveBeenCalled();
});
it('preserves the original grade revision through refresh and recovers a stale grade explicitly', async () => {
  mocks.getStudentSubmissions.mockResolvedValue({ submissions: [{ ...submission(50), assigned_marks: 40, feedback: 'Original', grade_revision: 'original-revision' }] });
  mocks.gradeSubmission.mockRejectedValue(Object.assign(new Error('Grade changed in another session'), { status: 409 }));
  mount(); await marking(); const marks = screen.getByRole('spinbutton', { name: /Assigned marks/ });
  fireEvent.change(marks, { target: { value: '70' } });
  mocks.getStudentSubmissions.mockResolvedValue({ submissions: [{ ...submission(50), assigned_marks: 90, feedback: 'New server feedback', grade_revision: 'latest-revision' }] });
  fireEvent.click(screen.getByRole('button', { name: 'Refresh submissions' })); await waitFor(() => expect(mocks.getStudentSubmissions).toHaveBeenCalledTimes(2));
  fireEvent.click(screen.getByRole('button', { name: /Save marks/ })); await screen.findByText(/Grade changed/);
  expect(mocks.gradeSubmission).toHaveBeenCalledWith(1, 70, 'Original', 'original-revision'); expect(marks.value).toBe('70');
  fireEvent.click(screen.getByRole('button', { name: 'Load latest marks (discard edits)' })); await waitFor(() => expect(marks.value).toBe('90'));
});

it('warns before a refresh discards unsaved research drafts and removes the warning after leaving the portal', async () => {
  const view = mount(); await ready(); fireEvent.change(comment(), { target: { value: 'Unsubmitted research comment' } });
  const refresh = new Event('beforeunload', { cancelable: true }); window.dispatchEvent(refresh);
  expect(refresh.defaultPrevented).toBe(true); expect(comment().value).toBe('Unsubmitted research comment');
  view.unmount(); const clean = new Event('beforeunload', { cancelable: true }); window.dispatchEvent(clean); expect(clean.defaultPrevented).toBe(false);
});

const marksInput = () => screen.getByRole('spinbutton', { name: /Assigned marks/ });
const feedbackInput = () => screen.getByRole('textbox', { name: 'Qualitative feedback' });
const chooseStudent = (name) => fireEvent.click(screen.getByRole('button', { name: new RegExp(name) }));
const twoSubmissions = () => [
  { ...submission(), id: 372, student_label: 'SIM-031', assigned_marks: null, feedback: '', grade_revision: 'original-372' },
  { ...submission(), id: 436, student_label: 'SIM-047', assigned_marks: 0, feedback: 'Saved zero', grade_revision: 'original-436' },
];

it('preserves independent grade drafts across submissions, tabs and refresh with the original revision', async () => {
  mocks.getStudentSubmissions.mockResolvedValue({ submissions: twoSubmissions() });
  mount(); await marking();
  fireEvent.change(marksInput(), { target: { value: '55' } });
  fireEvent.change(feedbackInput(), { target: { value: 'QA draft' } });
  chooseStudent('SIM-047');
  expect(marksInput().value).toBe('0'); expect(feedbackInput().value).toBe('Saved zero');
  fireEvent.change(feedbackInput(), { target: { value: 'Other draft' } });
  chooseStudent('SIM-031');
  expect(marksInput().value).toBe('55'); expect(feedbackInput().value).toBe('QA draft');
  fireEvent.click(screen.getByRole('button', { name: /CVI certification/ }));
  fireEvent.click(screen.getByRole('button', { name: /Code grading/ }));
  mocks.getStudentSubmissions.mockResolvedValue({ submissions: twoSubmissions().map((sub) => ({ ...sub, grade_revision: 'changed-on-server', feedback: 'New server feedback' })) });
  fireEvent.click(screen.getByRole('button', { name: 'Refresh submissions' }));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Refresh submissions' }).disabled).toBe(false));
  expect(feedbackInput().value).toBe('QA draft');
  chooseStudent('SIM-047'); expect(feedbackInput().value).toBe('Other draft');
  chooseStudent('SIM-031');
  expect(mocks.gradeSubmission).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Save marks' }));
  await waitFor(() => expect(mocks.gradeSubmission).toHaveBeenCalledWith(372, 55, 'QA draft', 'original-372'));
});

it('keeps failed grade drafts and clears only the saved submission draft after success', async () => {
  mocks.getStudentSubmissions.mockResolvedValue({ submissions: twoSubmissions() });
  mocks.gradeSubmission.mockRejectedValueOnce(new Error('Save failed'));
  mount(); await marking();
  fireEvent.change(marksInput(), { target: { value: '55' } });
  fireEvent.change(feedbackInput(), { target: { value: 'Keep this' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save marks' })); await screen.findByText(/Save failed/);
  chooseStudent('SIM-047'); fireEvent.change(feedbackInput(), { target: { value: 'Second draft' } });
  chooseStudent('SIM-031'); expect(marksInput().value).toBe('55'); expect(feedbackInput().value).toBe('Keep this');
  mocks.gradeSubmission.mockResolvedValue({ submission_id: 372, assigned_marks: 55, max_marks: 100, grade_revision: 'saved-372' });
  mocks.getStudentSubmissions.mockRejectedValueOnce(new Error('Refresh failed'));
  fireEvent.click(screen.getByRole('button', { name: 'Save marks' })); await screen.findByText(/Refresh failed/);
  expect(marksInput().value).toBe('55'); expect(feedbackInput().value).toBe('Keep this');
  expect(screen.queryByRole('status')).toBeNull();
  chooseStudent('SIM-047'); expect(feedbackInput().value).toBe('Second draft');
  expect(screen.getByRole('status').textContent).toContain('Unsaved draft');
});

it('warns for unsaved grades, blocks edits during save, and clears drafts on account changes', async () => {
  const pending = deferred(); mocks.gradeSubmission.mockReturnValue(pending.promise);
  const view = mount(); await marking();
  fireEvent.change(marksInput(), { target: { value: '70' } });
  const refresh = new Event('beforeunload', { cancelable: true }); window.dispatchEvent(refresh);
  expect(refresh.defaultPrevented).toBe(true);
  fireEvent.click(screen.getByRole('button', { name: 'Save marks' }));
  expect(marksInput().disabled).toBe(true); expect(feedbackInput().disabled).toBe(true);
  expect(screen.getByRole('button', { name: 'Refresh submissions' }).disabled).toBe(true);
  await act(async () => pending.resolve({ submission_id: 1, assigned_marks: 70, max_marks: 100, grade_revision: 'new' }));
  const savedRefresh = new Event('beforeunload', { cancelable: true }); window.dispatchEvent(savedRefresh);
  expect(savedRefresh.defaultPrevented).toBe(false);
  fireEvent.change(feedbackInput(), { target: { value: 'Private draft' } });
  mocks.user = { id: 99 }; view.rerender(<ExpertPortal />); await marking();
  expect(feedbackInput().value).toBe(''); expect(screen.queryByRole('status')).toBeNull();
});

it('switches expert controls and placeholders between English and Bengali while retaining drafts and content language', async () => {
  mocks.getExpertQueue.mockResolvedValue(queue([{ ...item('one'), question_text: 'প্রশ্নের বিবরণ', options: [{ id: 'a', text: 'প্রথম উত্তর' }] }]));
  const view = mount(); await ready();
  expect(screen.getByRole('heading', { name: 'Expert workbench' })).toBeTruthy();
  expect(screen.getByText('প্রশ্নের বিবরণ').lang).toBe('bn');
  expect(screen.getByText('প্রথম উত্তর').lang).toBe('bn');
  fireEvent.change(comment(), { target: { value: 'Keep bilingual draft' } });
  mocks.language = 'bn'; view.rerender(<ExpertPortal />);
  expect(screen.getByRole('heading', { name: 'এক্সপার্ট ওয়ার্কবেঞ্চ' })).toBeTruthy();
  expect(screen.getByRole('button', { name: 'পরের' })).toBeTruthy();
  expect(screen.getByPlaceholderText('শব্দচয়ন বা ডিস্ট্র্যাক্টর সংশোধনের প্রস্তাব...').value).toBe('Keep bilingual draft');
  fireEvent.click(screen.getByRole('button', { name: /কোড মূল্যায়ন/ }));
  expect(screen.getByRole('button', { name: 'নম্বর সংরক্ষণ করুন (Save marks)' })).toBeTruthy();
  mocks.language = 'en'; view.rerender(<ExpertPortal />);
  expect(screen.getByRole('textbox', { name: 'Qualitative feedback' }).placeholder).toBe('Write feedback on loop conditions, logic and code style…');
  expect(document.body.textContent).not.toMatch(/[\u0980-\u09ff]/u);
});

it('starts with the six assigned items, keeps earlier reviews reachable and preserves drafts through More', async () => {
  const assigned = ['one', 'two', 'three', 'four', 'five', 'six'].map((id) => ({ ...item(id), is_assigned: true }));
  const earlier = { ...item('earlier', { ...scores(3), feedback: 'Existing earlier comment' }), is_assigned: false };
  mocks.getExpertQueue.mockResolvedValue(queue([
    { ...item('outside'), is_assigned: false }, ...assigned, earlier,
  ]));
  mount(); await ready();
  expect(screen.getByText('Item 1 / 6')).toBeTruthy();
  expect(screen.getByRole('button', { name: 'CVI certification (6)' })).toBeTruthy();
  expect(screen.getByRole('button', { name: 'Assigned (6)' }).getAttribute('aria-pressed')).toBe('true');
  rate(4); fireEvent.change(comment(), { target: { value: 'Assigned draft' } });
  fireEvent.click(screen.getByRole('button', { name: 'Earlier work (1)' }));
  await screen.findByText('Item earlier'); selected(3);
  expect(comment().value).toBe('Existing earlier comment');
  fireEvent.click(screen.getByRole('button', { name: 'More (8)' }));
  expect(screen.getByText('Item 8 / 8')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Assigned (6)' }));
  await ready(); selected(4); expect(comment().value).toBe('Assigned draft');
  expect(mocks.submitExpertRating).not.toHaveBeenCalled();
});

it('advances within the assigned item list after a save without selecting hidden rows', async () => {
  const rows = [
    { ...item('one'), is_assigned: true },
    { ...item('hidden'), is_assigned: false },
    { ...item('two'), is_assigned: true },
  ];
  mocks.getExpertQueue.mockResolvedValue(queue(rows));
  mount(); await ready(); rate(4);
  mocks.getExpertQueue.mockResolvedValue(queue(rows.map((row) => row.id === 'one'
    ? { ...row, my_rating: { ...scores(4), feedback: '' } } : row)));
  fireEvent.click(screen.getByRole('button', { name: 'Submit rating' }));
  await screen.findByText('Item two');
  expect(screen.getByText('Item 2 / 2')).toBeTruthy();
  expect(screen.queryByText('Item hidden')).toBeNull();
});

it('shows assigned submissions and their own saved grades, with earlier work and More separate from the quota', async () => {
  mocks.getStudentSubmissions.mockResolvedValue({ submissions: [
    { ...submission(), id: 10, student_label: 'Outside submission', is_assigned: false, my_grade_completed: false },
    { ...submission(), id: 11, student_label: 'Assigned pending', is_assigned: true, my_grade_completed: false },
    { ...submission(), id: 12, student_label: 'Assigned completed', is_assigned: true, my_grade_completed: true,
      assigned_marks: 62, feedback: 'My saved assigned feedback', status: 'GRADED', graded_by: 'teacher-one' },
    { ...submission(), id: 13, student_label: 'Earlier legacy student', is_assigned: false, my_grade_completed: true,
      assigned_marks: 0, feedback: 'My earlier zero feedback', status: 'GRADED', graded_by: 'teacher-one' },
  ] });
  mount(); await marking();
  expect(screen.getByRole('button', { name: 'Code grading (2)' })).toBeTruthy();
  expect(screen.queryByText('Outside submission')).toBeNull();
  expect(screen.queryByText('Earlier legacy student')).toBeNull();
  expect(marksInput().value).toBe('');
  fireEvent.change(marksInput(), { target: { value: '71' } });
  fireEvent.change(feedbackInput(), { target: { value: 'Keep assigned draft' } });
  chooseStudent('Assigned completed');
  expect(marksInput().value).toBe('62'); expect(feedbackInput().value).toBe('My saved assigned feedback');
  fireEvent.click(screen.getByRole('button', { name: 'Earlier work (2)' }));
  chooseStudent('Earlier legacy student');
  expect(marksInput().value).toBe('0'); expect(feedbackInput().value).toBe('My earlier zero feedback');
  expect(screen.queryByText('Assigned pending')).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'More (4)' }));
  chooseStudent('Outside submission'); expect(marksInput().value).toBe('');
  fireEvent.click(screen.getByRole('button', { name: 'Refresh submissions' }));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Refresh submissions' }).disabled).toBe(false));
  expect(screen.getAllByText('Outside submission')).toHaveLength(2);
  expect(marksInput().value).toBe('');
  fireEvent.click(screen.getByRole('button', { name: 'Assigned (2)' }));
  await screen.findAllByText('Assigned pending');
  expect(marksInput().value).toBe('71'); expect(feedbackInput().value).toBe('Keep assigned draft');
  expect(mocks.gradeSubmission).not.toHaveBeenCalled();
});

it('allows More from an empty assigned queue without inventing assignments', async () => {
  mocks.getExpertQueue.mockResolvedValue(queue([{ ...item('outside'), is_assigned: false }]));
  mocks.getStudentSubmissions.mockResolvedValue({ submissions: [{ ...submission(), is_assigned: false }] });
  mount();
  await screen.findByText('No items in this work list. Choose More to review other items.');
  fireEvent.click(screen.getByRole('button', { name: 'More (1)' }));
  await screen.findByText('Item outside');
  fireEvent.click(screen.getByRole('button', { name: 'Code grading (0)' }));
  await screen.findByText('No submissions in this work list. Choose More to review other submissions.');
  fireEvent.click(screen.getByRole('button', { name: 'More (1)' }));
  await screen.findByRole('button', { name: 'Save marks' });
});

it('keeps legacy queues without assignment metadata fully available by default', async () => {
  mount(); await ready();
  expect(screen.getByText('Item 1 / 2')).toBeTruthy();
  next(); await screen.findByText('Item two');
  fireEvent.click(screen.getByRole('button', { name: /Code grading/ }));
  await screen.findByRole('button', { name: 'Save marks' });
  expect(screen.getByRole('button', { name: 'Assigned (1)' }).getAttribute('aria-pressed')).toBe('true');
});
