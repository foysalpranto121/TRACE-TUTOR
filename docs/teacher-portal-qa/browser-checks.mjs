import { chromium } from './browser-runtime/node_modules/playwright/index.mjs';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';
const dir = path.dirname(fileURLToPath(import.meta.url));
const axe = await fs.readFile(path.join(dir, 'browser-runtime/node_modules/axe-core/axe.min.js'), 'utf8');
const screenshots = path.join(dir, 'screenshots'); await fs.mkdir(screenshots, { recursive: true });
const criteria = ['Curriculum alignment', 'Technical accuracy', 'Language clarity', 'Grade 11-12 difficulty', 'Defensible answerability'];
const model = { configured: true, provider: 'openai', primary_model: 'gpt-5-mini', fallback_models: [] };
const results = [];
const browser = await chromium.launch({ executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true });
try {
for (const [name, viewport, role] of [['desktop-teacher', { width: 1440, height: 1000 }, 'EXPERT_TEACHER'], ['mobile-teacher', { width: 390, height: 844 }, 'EXPERT_TEACHER'], ['mobile-student', { width: 390, height: 844 }, 'STUDENT']]) {
  const context = await browser.newContext({ viewport, reducedMotion: 'reduce' });
  const page = await context.newPage(); const errors = []; const requests = []; let refreshes = 0; let submitted = 0; let profileFailure = false;
  page.on('pageerror', error => errors.push(error.message));
  const user = { id: role === 'STUDENT' ? 902 : 901, username: 'disposable-qa', full_name: 'Disposable QA User', role, language: 'en', arm: 'REASONING_VISIBLE', enrolled_arm: 'REASONING_VISIBLE', arm_self_select: true, consent_given: true };
  const queue = { items_to_review: [1, 2].map(id => ({ id: 'qa-item-' + id, title: 'Disposable Item ' + id, question_text: 'Safe QA question ' + id, exam_type: 'pre', chapter: 'Chapter 5', type: 'concept_mcq', ratings_count: 0, rating_revision: null, my_rating: null })), cvi_stats: { total_items: 2, rated_items: 0, expert_count: 0, ratings_count: 0, i_cvi_pass_rate: null, s_cvi_ave: null } };
  let rows = [{ id: 1, student_label: 'QA-TT-0001', participant_code: 'QA-TT-0001', exam_type: 'pre', grading_status: 'graded', score_pct: null, assigned_marks: null, max_marks: 100, feedback: '', grade_revision: null, code_answers: [], status: 'PENDING_REVIEW' }];
  let queryResolve; let holdQuery = false;
  await context.route('**/*', async route => {
    const url = new URL(route.request().url());
    // Allow only the editor's existing CDN GET assets; all external writes stay blocked.
    if (url.hostname === 'cdn.jsdelivr.net' && route.request().method() === 'GET' && url.pathname.startsWith('/npm/monaco-editor@')) { await route.continue(); return; }
    if (url.hostname !== '127.0.0.1') { await route.abort('blockedbyclient'); return; }
    if (!url.pathname.startsWith('/api/')) { await route.continue(); return; }
    const req = route.request(); requests.push({ path: url.pathname, method: req.method() });
    const respond = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    const body = req.method() === 'GET' ? {} : req.postDataJSON();
    switch (url.pathname) {
      case '/api/accounts/login/': return respond({ user, token: 'a'.repeat(40) });
      case '/api/accounts/me/': return respond(user);
      case '/api/accounts/profile/':
        if (profileFailure) return respond({ error: 'QA profile save failed' }, 500);
        if (body.full_name === '') return respond({ error: 'Full name cannot be empty.', fields: { full_name: 'Required' } }, 400);
        if (body.assigned_arm) user.arm = body.assigned_arm;
        if (body.full_name) user.full_name = body.full_name;
        if (body.school_name) user.school_name = body.school_name;
        return respond(user);
      case '/api/telemetry/log/': return respond({ logged: true });
      case '/api/dashboard/': return respond({ stats: {}, assessments: {}, problems: [], recent: [], daily: [], tutor_model: model, tutor_availability: { available: true }, ...(role === 'STUDENT' ? {} : { overview: { participants: 0, students: 0, submissions: 0, expert_ratings: 0, expert_grades: 0, events: 0, active_today: 0, code_runs: 0, help_requests: 0, arms: {} } }) });
      case '/api/curriculum/status/': return respond({ engine: { vector_count: 0 }, ingest: { stage: 'idle' } });
      case '/api/code/run/': return respond({ status: body.mode === 'check' ? 'OK' : 'SUCCESS', diagnostics: [], compile_output: '', passed_count: 1, test_results: [{ id: 1, input: '3', expected: '6', actual: '6', passed: true }], sandbox: 'mock' });
      case '/api/code/status/': return respond({ ready: false, html: true, sandbox: { tier: 'none', allowed: false } });
      case '/api/expert/reviews/': return role === 'STUDENT' ? respond({ error: 'Forbidden' }, 403) : respond(queue);
      case '/api/expert/submissions/': refreshes++; return respond({ submissions: rows });
      case '/api/expert/rating/': {
        submitted++; const item = queue.items_to_review.find(item => item.id === body.item_id);
        assert.equal(Object.keys(body.ratings).length, 5); item.my_rating = { ...body.ratings, feedback: body.feedback }; item.rating_revision = 'qa-saved'; item.ratings_count = 1;
        return respond({ status: 'success', rated: true, item_id: item.id, rating_revision: item.rating_revision });
      }
      case '/api/expert/grade/': {
        assert.ok(Number.isInteger(body.assigned_marks)); assert.ok(body.assigned_marks >= 0 && body.assigned_marks <= 100);
        rows[0] = { ...rows[0], assigned_marks: body.assigned_marks, feedback: body.feedback, status: 'GRADED', grade_revision: 'qa-grade' };
        return respond({ status: 'success', submission_id: 1, assigned_marks: body.assigned_marks, max_marks: 100, grade_revision: 'qa-grade', graded_at: new Date().toISOString() });
      }
      case '/api/tutor/query/':
        if (holdQuery) await new Promise(resolve => { queryResolve = resolve; });
        return respond({ ai_status: 'live', provider: 'openai', model: 'gpt-5-mini', cached: true, direct_answer: '1', rag_answer: { textbook_rule: 'Remainder operator', textbook_explanation: 'Disposable textbook evidence', curriculum_citation: 'QA textbook p.1' }, independent_ai_answer: { chat_answer: '7 % 2 = 1' }, retrieved_passages: [{ id: 'qa-passage', source_ref: 'QA p.1', passage: 'Disposable retrieved passage' }] });
      default: throw Error('Unmocked API request: ' + url.pathname);
    }
  });
  await page.goto('http://127.0.0.1:4174/login');
  await page.getByRole('textbox', { name: /Username or email|ইউজারনেম বা ইমেইল/ }).fill('disposable-qa');
  await page.getByLabel(/^(Password|পাসওয়ার্ড)/).fill('Disposable-QA-only');
  await page.getByRole('button', { name: /^(Sign in|সাইন ইন)$/ }).click();
  if (role === 'EXPERT_TEACHER') {
    await page.getByText('Disposable Item 1', { exact: true }).waitFor();
    assert.equal(await page.getByRole('button', { name: /Submit/ }).isDisabled(), true);
    for (const label of criteria) await page.getByRole('button', { name: label + ': 4 of 4', exact: true }).click();
    await page.getByRole('textbox', { name: /Expert comments/ }).fill('First independent QA draft');
    await page.getByRole('button', { name: 'পরের', exact: true }).click();
    for (const label of criteria) await page.getByRole('button', { name: label + ': 2 of 4', exact: true }).click();
    await page.getByRole('textbox', { name: /Expert comments/ }).fill('Second independent QA draft');
    await page.getByRole('button', { name: 'আগের', exact: true }).click();
    assert.equal(await page.getByRole('textbox', { name: /Expert comments/ }).inputValue(), 'First independent QA draft');
    for (const label of criteria) assert.equal(await page.getByRole('button', { name: label + ': 4 of 4', exact: true }).getAttribute('aria-pressed'), 'true');
    assert.equal(submitted, 0);
    await page.screenshot({ path: path.join(screenshots, name + '-cvi.png'), fullPage: true });
    await page.addScriptTag({ content: axe });
    const cviAxe = await page.evaluate(async () => (await window.axe.run()).violations.map(v => ({ id: v.id, impact: v.impact, nodes: v.nodes.map(n => n.target) })));
    await page.getByRole('button', { name: /Submit/ }).click();
    await page.getByText('Disposable Item 2', { exact: true }).waitFor();
    assert.equal(await page.getByRole('textbox', { name: /Expert comments/ }).inputValue(), 'Second independent QA draft');
    await page.getByRole('button', { name: 'আগের', exact: true }).click();
    assert.equal(await page.getByRole('textbox', { name: /Expert comments/ }).inputValue(), 'First independent QA draft');
    page.once('dialog', dialog => dialog.accept()); await page.reload();
    await page.getByText('Disposable Item 1', { exact: true }).waitFor();
    assert.equal(await page.getByRole('textbox', { name: /Expert comments/ }).inputValue(), 'First independent QA draft');
    await page.getByRole('button', { name: 'পরের', exact: true }).click();
    assert.equal(await page.getByRole('textbox', { name: /Expert comments/ }).inputValue(), '');
    await page.getByRole('button', { name: /কোড মূল্যায়ন/ }).click();
    await page.getByRole('button', { name: 'Refresh submissions', exact: true }).waitFor();
    assert.equal(await page.getByText('Score unavailable', { exact: true }).count(), 1);
    await page.screenshot({ path: path.join(screenshots, name + '-missing-score.png'), fullPage: true });
    assert.equal(await page.getByText('Score unavailable', { exact: true }).evaluate(el => el.getBoundingClientRect().right <= el.closest('.tint-card').getBoundingClientRect().right), true);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
    const refresh = page.getByRole('button', { name: 'Refresh submissions', exact: true });
    await refresh.focus(); await page.keyboard.press('Tab'); await page.keyboard.press('Shift+Tab'); assert.equal(await refresh.evaluate(el => el === document.activeElement), true);
    const outline = await refresh.evaluate(el => ({ style: getComputedStyle(el).outlineStyle, width: getComputedStyle(el).outlineWidth }));
    assert.notEqual(outline.style, 'none'); assert.notEqual(outline.width, '0px');
    const before = refreshes; rows[0].score_pct = 0; await refresh.press('Enter'); await page.getByText('0%', { exact: true }).waitFor(); assert.ok(refreshes > before);
    rows[0].score_pct = 85; await refresh.press('Space'); await page.getByText('85%', { exact: true }).waitFor();
    await page.getByRole('spinbutton', { name: /Assigned marks/ }).fill('70'); await page.getByRole('button', { name: /Save marks/ }).click();
    await page.getByText(/saved.*70/i).waitFor();
    await page.screenshot({ path: path.join(screenshots, name + '-marking.png'), fullPage: true });
    await page.addScriptTag({ content: axe });
    const markingAxe = await page.evaluate(async () => (await window.axe.run()).violations.map(v => ({ id: v.id, impact: v.impact, nodes: v.nodes.map(n => n.target) })));
    assert.deepEqual(cviAxe, []); assert.deepEqual(markingAxe, []);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
    results.push({ name, cviDrafts: 'passed', explicitSubmit: 'passed', refreshDiscardWarning: 'passed', scores: 'passed', keyboardRefresh: 'passed', focusOutline: outline, gradeSave: 'passed', noHorizontalOverflow: true, cviAxe, markingAxe });
  } else {
    await page.goto('http://127.0.0.1:4174/expert'); await page.waitForURL('**/dashboard');
    assert.equal(requests.some(req => req.path.startsWith('/api/expert/')), false);
    results.push({ name, frontendRoleBoundary: 'passed' });
  }
  await page.goto('http://127.0.0.1:4174/dashboard'); await page.getByText(/OpenAI · gpt-5-mini/).first().waitFor();
  const search = page.getByRole('combobox', { name: 'Search topics and tasks' });
  await search.fill('does-not-exist-qa'); await search.press('Enter'); await page.getByText('No matching topics or tasks found.').waitFor();
  await search.fill(''); await search.press('Enter'); assert.equal(await page.getByRole('listbox').count(), 0);
  await search.fill('loop'); await page.getByRole('listbox', { name: 'Topics and tasks' }).waitFor();
  await search.press('ArrowDown'); assert.ok(await search.getAttribute('aria-activedescendant')); await search.press('Enter'); await page.waitForURL('**/workspace?problem=*');
  await page.getByTitle('Configured primary: OpenAI · gpt-5-mini').waitFor();
  holdQuery = true; await page.getByRole('textbox', { name: /Ask the tutor/ }).fill('7 % 2'); await page.getByRole('button', { name: 'Ask', exact: true }).click();
  await page.getByTitle('Configured primary: OpenAI · gpt-5-mini; Response pending').waitFor();
  assert.equal(await page.getByText('Gemini', { exact: true }).count(), 0);
  while (!queryResolve) await new Promise(resolve => setTimeout(resolve, 10)); queryResolve();
  await page.getByText('7 % 2 = 1', { exact: true }).waitFor();
  await page.getByRole('button', { name: 'Textbook', exact: true }).click(); await page.getByText('Disposable textbook evidence', { exact: true }).waitFor();
  assert.equal(await page.getByText('7 % 2 = 1', { exact: true }).count(), 0);
  await page.getByRole('button', { name: 'AI', exact: true }).click(); await page.getByText('7 % 2 = 1', { exact: true }).waitFor();
  await page.getByRole('button', { name: 'Dual', exact: true }).click(); await page.getByText('Disposable retrieved passage', { exact: true }).waitFor();
  await page.screenshot({ path: path.join(screenshots, name + '-workspace.png'), fullPage: true });
  results[results.length - 1].search = 'passed'; results[results.length - 1].pendingCachedLabelsAndTabs = 'passed'; results[results.length - 1].pageErrors = errors; assert.deepEqual(errors, []);
  if (role === 'EXPERT_TEACHER') {
    await page.getByRole('button', { name: 'Run Code', exact: true }).click();
    await page.getByText('1/1 test cases passed', { exact: true }).waitFor();
    results[results.length - 1].teacherCodeRunMocked = 'passed';
    await page.goto('http://127.0.0.1:4174/profile');
    await page.getByRole('textbox', { name: /^Full name/ }).fill('Updated Disposable Teacher');
    await page.getByLabel(/^Institution/).first().fill('Disposable QA School');
    profileFailure = true;
    await page.getByRole('button', { name: 'Save changes', exact: true }).click();
    await page.getByText('QA profile save failed', { exact: true }).waitFor();
    assert.equal(await page.getByRole('textbox', { name: /^Full name/ }).inputValue(), 'Updated Disposable Teacher');
    profileFailure = false; await page.getByRole('button', { name: 'Save changes', exact: true }).click();
    await page.getByText('Profile saved.', { exact: true }).waitFor(); await page.reload();
    assert.equal(await page.getByRole('textbox', { name: /^Full name/ }).inputValue(), 'Updated Disposable Teacher');
    await page.getByRole('button', { name: /Answer-Only.*The tutor gives/ }).click();
    await page.getByText(/Tutor mode switched to Answer-Only/).waitFor(); await page.reload();
    assert.equal(await page.getByRole('button', { name: /Answer-Only.*The tutor gives/ }).getAttribute('aria-pressed'), 'true');
    await page.getByRole('button', { name: /Reasoning-Visible.*The tutor shows/ }).click();
    await page.getByText(/Tutor mode switched to Reasoning-Visible/).waitFor();
    results[results.length - 1].teacherProfileSaveFailureAndReload = 'passed';
    results[results.length - 1].teacherArmSwitchAndReload = 'passed';
  }
  await context.close();
}
console.log(JSON.stringify(results, null, 2));
} finally { await fs.writeFile(path.join(dir, 'browser-results.json'), JSON.stringify(results, null, 2)); await browser.close(); }
