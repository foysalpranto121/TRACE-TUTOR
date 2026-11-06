import { chromium } from '../browser-runtime/node_modules/playwright/index.mjs';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';
const dir = path.dirname(fileURLToPath(import.meta.url));
const origin = 'https://trace.musfiqurtuhin.me';
assert.equal(new URL(origin).hostname, 'trace.musfiqurtuhin.me');
const fixture = JSON.parse(await fs.readFile(path.join(dir, 'fixture-private.json'), 'utf8'));
process.env.TRACE_QA_PASSWORD = fixture.password;
const axe = await fs.readFile(path.join(dir, '../browser-runtime/node_modules/axe-core/axe.min.js'), 'utf8');
const criteria = ['Curriculum alignment', 'Technical accuracy', 'Language clarity', 'Grade 11-12 difficulty', 'Defensible answerability'];
const results = [];
const browser = await chromium.launch({ executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true });
async function login(page, user) {
  await page.goto(origin + '/login');
  await page.getByRole('textbox', { name: /Username or email|ইউজারনেম বা ইমেইল/ }).fill(user);
  await page.getByLabel(/^(Password|পাসওয়ার্ড)/).fill(process.env.TRACE_QA_PASSWORD);
  await page.getByRole('button', { name: /^(Sign in|সাইন ইন)$/ }).click();
  await page.waitForURL(user.includes('teacher') ? '**/expert' : '**/dashboard');
}
async function api(page, endpoint, body) {
  const token = await page.evaluate(() => sessionStorage.getItem('trace_auth_token') || localStorage.getItem('trace_auth_token'));
  const response = await page.request.fetch(origin + '/api/' + endpoint, { method: body === undefined ? 'GET' : 'POST',
    headers: { Authorization: 'Token ' + token }, ...(body === undefined ? {} : { data: body }) });
  return { status: response.status(), body: await response.json() };
}
async function scan(page) { await page.addScriptTag({ content: axe }); return page.evaluate(async () => (await window.axe.run()).violations.map(v => ({ id: v.id, targets: v.nodes.map(n => n.target) }))); }
async function setCode(page, code) { await page.waitForFunction(() => window.monaco?.editor.getModels().length > 0); await page.evaluate(value => window.monaco.editor.getModels()[0].setValue(value), code); }
async function runEditor(page) {
  const waiting = page.waitForResponse(r => r.url().endsWith('/api/code/run/') && r.request().method() === 'POST' && r.request().postDataJSON().mode === 'run', { timeout: 90000 });
  await page.getByRole('button', { name: 'Run Code', exact: true }).click();
  const response = await waiting; assert.equal(response.status(), 200); return response.json();
}
try {
for (const [name, viewport] of [['desktop', { width: 1440, height: 1000 }], ['mobile', { width: 390, height: 844 }]]) {
  const context = await browser.newContext({ viewport, reducedMotion: 'reduce' }); const page = await context.newPage(); page.setDefaultTimeout(45000);
  const errors = []; const requests = []; page.on('pageerror', e => errors.push(e.message));
  page.on('response', response => { if (response.url().startsWith(origin + '/api/')) requests.push({ path: new URL(response.url()).pathname, status: response.status() }); });
  // Real requests pass through unchanged. Only non-editor external requests are blocked.
  await context.route('**/*', async route => { const url = new URL(route.request().url());
    if (url.origin === origin && ['/api/tutor/query/', '/api/assessment/submit/'].includes(url.pathname)) return route.abort('blockedbyclient');
    if (url.origin === origin && url.pathname === '/api/expert/grade/' && route.request().method() === 'POST') {
      const body = route.request().postDataJSON();
      assert.ok([fixture.missing_id, fixture.zero_id].includes(body.submission_id), 'Grade must target a disposable fixture');
    }
    if (url.origin === origin || (url.hostname === 'cdn.jsdelivr.net' && route.request().method() === 'GET' && url.pathname.startsWith('/npm/monaco-editor@'))) return route.continue();
    return route.abort('blockedbyclient'); });
  await login(page, fixture.teacher);
  const queue = (await api(page, 'expert/reviews/')).body.items_to_review; assert.ok(queue.length > 1);
  await page.getByText(queue[0].title, { exact: true }).waitFor();
  for (const label of criteria) await page.getByRole('button', { name: label + ': 4 of 4', exact: true }).click();
  const comment = name + ' real disposable review'; await page.getByRole('textbox', { name: /Expert comments/ }).fill(comment);
  await page.getByRole('button', { name: 'পরের', exact: true }).click();
  for (const label of criteria) await page.getByRole('button', { name: label + ': 2 of 4', exact: true }).click();
  await page.getByRole('textbox', { name: /Expert comments/ }).fill('Independent unsent draft');
  await page.getByRole('button', { name: 'আগের', exact: true }).click();
  assert.equal(await page.getByRole('textbox', { name: /Expert comments/ }).inputValue(), comment);
  const cviAxe = await scan(page); assert.deepEqual(cviAxe, []);
  await page.getByRole('button', { name: /\(Submit\)|\(Update\)/ }).click();
  await page.getByText(queue[1].title, { exact: true }).waitFor();
  assert.equal(await page.getByRole('textbox', { name: /Expert comments/ }).inputValue(), 'Independent unsent draft');
  assert.equal((await api(page, 'expert/reviews/')).body.items_to_review[0].my_rating.feedback, comment);
  page.once('dialog', d => d.accept()); await page.reload();
  await page.getByText(queue[0].title, { exact: true }).waitFor();
  assert.equal(await page.getByRole('textbox', { name: /Expert comments/ }).inputValue(), comment);
  await page.getByRole('button', { name: /কোড/ }).click();
  await page.getByRole('button', { name: 'Refresh submissions', exact: true }).waitFor();
  await page.getByText('Score unavailable', { exact: true }).first().waitFor();
  const rows = (await api(page, 'expert/submissions/')).body.submissions;
  const missing = rows.find(r => r.id === fixture.missing_id); const zero = rows.find(r => r.id === fixture.zero_id); assert.ok(missing && zero); assert.equal(missing.score_pct, null); assert.equal(zero.score_pct, 0);
  const zeroButton = page.getByRole('button').filter({ hasText: fixture.student_code }).filter({ hasText: /0%/ }); await zeroButton.click(); await page.getByText('0%', { exact: true }).waitFor();
  await page.getByRole('button').filter({ hasText: fixture.student_code }).filter({ hasText: /Score unavailable/ }).click();
  await page.getByRole('spinbutton', { name: /Assigned marks/ }).fill(name === 'desktop' ? '70' : '80');
  await page.getByRole('button', { name: /Save marks/ }).click(); await page.getByText(/saved.*(70|80)/i).waitFor();
  const fresh = (await api(page, 'expert/submissions/')).body.submissions.find(r => r.id === missing.id);
  const updated = await api(page, 'expert/grade/', { submission_id: missing.id, assigned_marks: 88, feedback: 'Real second-session edit', expected_revision: fresh.grade_revision }); assert.equal(updated.status, 200);
  const refresh = page.getByRole('button', { name: 'Refresh submissions', exact: true });
  await page.waitForFunction(() => !document.querySelector('button[aria-label="Refresh submissions"]').disabled);
  await refresh.focus(); await page.keyboard.press('Tab'); await page.keyboard.press('Shift+Tab');
  assert.equal(await refresh.evaluate(el => el === document.activeElement), true);
  assert.notEqual(await refresh.evaluate(el => getComputedStyle(el).outlineStyle), 'none');
  const loaded = page.waitForResponse(r => r.url().endsWith('/api/expert/submissions/') && r.request().method() === 'GET'); await refresh.press('Enter'); assert.equal((await loaded).status(), 200);
  await page.getByText('88 / 100', { exact: true }).waitFor(); const markingAxe = await scan(page); assert.deepEqual(markingAxe, []);
  await page.screenshot({ path: path.join(dir, 'screenshots/live-' + name + '-marking.png'), fullPage: true });
  await page.goto(origin + '/dashboard'); const search = page.getByRole('combobox', { name: 'Search topics and tasks' });
  await search.fill('no-such-topic-live-qa'); await search.press('Enter'); await page.getByText('No matching topics or tasks found.').waitFor();
  await search.fill('loop'); await page.getByRole('listbox').waitFor(); await search.press('ArrowDown'); await search.press('Enter'); await page.waitForURL('**/workspace?problem=*');
  await page.goto(origin + '/workspace?problem=prob_c_loop_101');
  await setCode(page, '#include <stdio.h>\nint main(){int n; if(scanf("%d",&n)!=1)return 2; printf("Sum = %d\\n",n*(n+1)/2);return 0;}');
  const correct = await runEditor(page); assert.equal(correct.sandbox, 'docker'); assert.equal(correct.status, 'SUCCESS'); assert.equal(correct.passed_count, correct.test_results.length);
  await page.getByText(correct.passed_count + '/' + correct.test_results.length + ' test cases passed', { exact: true }).waitFor();
  if (name === 'desktop') {
    await setCode(page, 'int main(){this is not C;}'); const compileError = await runEditor(page); assert.equal(compileError.status, 'COMPILE_ERROR'); assert.ok(compileError.diagnostics.length);
    await setCode(page, 'int main(){return 7;}'); const runtime = await runEditor(page); assert.equal(runtime.status, 'RUNTIME_ERROR'); await page.getByText('RUNTIME ERROR', { exact: true }).first().waitFor();
  }
  const dashboard = await api(page, 'dashboard/'); assert.equal(dashboard.status, 200);
  assert.equal(dashboard.body.tutor_model.provider, 'openai'); assert.equal(dashboard.body.tutor_model.primary_model, 'gpt-5-mini');
  await page.getByTitle(/Configured primary: OpenAI.*gpt-5-mini/).first().waitFor();
  assert.equal(requests.some(r => r.path === '/api/tutor/query/'), false, 'No paid tutor query permitted');
  await page.screenshot({ path: path.join(dir, 'screenshots/live-' + name + '-workspace.png'), fullPage: true });
  assert.deepEqual(errors, []); assert.equal(requests.some(r => r.status >= 400), false, JSON.stringify(requests.filter(r => r.status >= 400))); results.push({ name, realLogin: true, cviPersistence: true, independentDrafts: true, gradeUpdate: true, realRefresh: true, nullAndZero: true, search: true, actualDockerRun: correct.status, runResults: correct.test_results, cviAxe, markingAxe, errors, requests });
  await context.close();
}
const studentContext = await browser.newContext({ viewport: { width: 390, height: 844 } }); const studentPage = await studentContext.newPage(); await login(studentPage, fixture.student);
assert.equal((await api(studentPage, 'dashboard/')).status, 200);
await studentPage.getByText('Pre-Test (Baseline)', { exact: true }).locator('..').locator('..').getByText('Score unavailable', { exact: true }).waitFor();
assert.equal(await studentPage.getByText('null%', { exact: true }).count(), 0);
await studentPage.screenshot({ path: path.join(dir, 'screenshots/live-mobile-student-dashboard.png'), fullPage: true });
await studentPage.goto(origin + '/expert'); await studentPage.waitForURL('**/dashboard');
for (const endpoint of ['expert/reviews/', 'expert/submissions/', 'expert/certification/']) assert.ok([401, 403].includes((await api(studentPage, endpoint)).status));
for (const endpoint of ['expert/rating/', 'expert/grade/']) assert.ok([401, 403].includes((await api(studentPage, endpoint, {})).status));
results.push({ name: 'mobile-student', realLogin: true, frontendAndBackendRoleIsolation: true }); await studentContext.close();
console.log(JSON.stringify(results, null, 2));
} finally { await fs.writeFile(path.join(dir, 'production-browser-results.json'), JSON.stringify(results, null, 2)); await browser.close(); }
