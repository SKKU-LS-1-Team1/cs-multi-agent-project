// Run: node --test tests/admin-state.test.mjs (from frontend/).
// Execute the real TypeScript modules with browser storage and API boundaries mocked.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import { webcrypto } from 'node:crypto';
import ts from 'typescript';

const noop = () => {};
const toast = Object.assign(noop, { error: noop });
function load(file, imports, globals = {}) {
  const exports = {};
  const code = ts.transpileModule(fs.readFileSync(new URL(`../src/admin/${file}`, import.meta.url), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  vm.runInNewContext(code, { exports, require: id => {
    assert.ok(id in imports, `Unmocked dependency: ${id}`);
    return imports[id];
  }, crypto: webcrypto, setTimeout, ...globals });
  return exports;
}
function actionFixture() {
  const state = { tickets: [], closed: 0, calls: 0, resolve: async () => false };
  const actions = load('lib/actions.ts', {
    sonner: { toast },
    './logic': { recommend: () => undefined, resourceReason: () => '', FRONTLINE: 'CS', signedIn: 'tester',
      answerContext: () => ({ references: [] }), record: (t, kind, text, extra) => t.events.push({ kind, text, ...extra }) },
    './store': { tickets: state.tickets, commit: noop, closeModal: () => state.closed++ },
    './api-sync': { isApiTicket: t => t.source === 'api', resolveViaApi: async t => { state.calls++; return state.resolve(t); } },
  });
  return { state, actions };
}
const ticket = () => ({ id: 'T-X', source: 'api', stage: 0, status: '발송 완료', sla: '1h', events: [] });
const input = { cause: '확인 원인', action: '확인 조치', result: '결과', verification: '확인 근거', outcome: 'resolved' };

test('local IDs handle mixed formats, empty lists, and repeated creation', () => {
  const { state, actions } = actionFixture();
  state.tickets.push({ id: 'T-HEX123' }, { id: 'CSV1-000NaN' }, { id: 'CSV1-000057' });
  assert.equal(actions.createTicket({ title: 'first' }, []), 'CSV1-000058');
  assert.equal(actions.createTicket({ title: 'next' }, []), 'CSV1-000059');
  state.tickets.splice(0);
  assert.equal(actions.createTicket({ title: 'empty' }, []), 'CSV1-000001');
});
test('failed completion preserves state, input and open form; retry succeeds', async () => {
  const { state, actions } = actionFixture(); const t = ticket();
  await actions.completeTicket(t, input);
  assert.equal(t.stage, 0); assert.equal(t.status, '발송 완료'); assert.equal(t.events.length, 0);
  assert.equal(state.closed, 0); assert.equal(t.resolutionDraft.cause, input.cause);
  state.resolve = async t => { t.stage = 5; t.status = '완료'; return true; };
  await actions.completeTicket(t, input);
  assert.equal(t.stage, 5); assert.equal(t.events.length, 1); assert.equal(state.closed, 1);
  assert.equal(t.resolution.cause, input.cause); assert.equal(t.resolutionDraft, undefined);
});
test('completion waits for success and ignores duplicate submission', async () => {
  const { state, actions } = actionFixture(); const t = ticket(); let release;
  state.resolve = row => new Promise(resolve => { release = () => { row.stage = 5; resolve(true); }; });
  const pending = actions.completeTicket(t, input);
  await actions.completeTicket(t, input);
  assert.equal(state.calls, 1); assert.equal(t.stage, 0); assert.equal(t.events.length, 0);
  release(); await pending; assert.equal(t.events.length, 1);
});
test('local completion never calls the API', async () => {
  const { state, actions } = actionFixture(); const t = { ...ticket(), source: 'local' };
  await actions.completeTicket(t, input);
  assert.equal(t.stage, 5); assert.equal(state.calls, 0);
});
test('care drafts preserve edited body and target metadata across reload without marking sent', () => {
  const disk = new Map();
  const imports = { react: { useSyncExternalStore: noop }, './logic': { signedIn: 'tester' } };
  const globals = { localStorage: { getItem: k => disk.get(k) ?? null, setItem: (k, v) => disk.set(k, v) } };
  const care = load('lib/care.ts', imports, globals);
  care.addCareAction('C-1', 'notice_draft', 'Edited text\nSecond line', undefined, { ticketIds: ['T-X'], language: 'en' });
  const restored = load('lib/care.ts', imports, globals); const row = restored.recordOf('C-1');
  assert.equal(row.actions[0].text, 'Edited text\nSecond line'); assert.equal(row.actions[0].ticketIds[0], 'T-X');
  assert.equal(row.actions[0].language, 'en'); assert.equal(row.followUp, undefined); assert.equal(restored.careStatus(row), 'none');
  care.addCareAction('C-2', 'notice', 'existing action'); care.resolveCare('C-2', true);
  care.addCareAction('C-2', 'notice_draft', 'new draft'); assert.equal(care.careStatus(care.recordOf('C-2')), 'resolved');
});
function completionFixture() {
  return load('lib/logic.ts', {
    '@admin/data/knowledge-data': { caseCatalog: [] },
    './auth': { currentAccount: () => undefined, ACCOUNTS: [
      { userId: '1', name: 'Doyeon Kim', role: 'LEAD' }, { userId: '2', name: 'Minji Park' },
      { userId: '3', name: 'Jun Lee' }, { userId: '4', name: 'Hana Choi' },
    ] },
    './store': { tickets: [], onBeforeCommit: noop, save: noop },
  }).completionDraft;
}
test('completion draft does not turn a hypothesis or specialist reply into confirmed cause/action', () => {
  const draft = completionFixture();
  const d = draft({ ...ticket(), events: [{ kind: 'expert', text: 'A fault is suspected', department: 'QA' }] });
  assert.equal(d.cause, ''); assert.equal(d.outcome, '');
  assert.ok(d.action.includes('수신')); assert.ok(!d.action.includes('반영')); assert.ok(!d.action.includes('답변'));
  assert.equal(d.result, '');
});
test('completion draft distinguishes received reply from verified resolution', () => {
  const draft = completionFixture();
  const d = draft({ ...ticket(), customerOutcome: 'resolved', events: [
    { kind: 'sent', purpose: 'answer' }, { kind: 'customer-followup', text: 'Still broken', customerResult: 'needs-support' },
  ] });
  assert.equal(d.outcome, ''); assert.ok(d.result.includes('회신이 있으나')); assert.ok(!d.result.includes('회신이 없어'));
});
test('completion draft uses explicit latest customer result, not an outcome before a newer send', () => {
  const draft = completionFixture();
  const reply = { kind: 'customer-followup', customerResult: 'resolved' }, sent = { kind: 'sent', purpose: 'answer' };
  assert.equal(draft({ ...ticket(), events: [sent, reply] }).outcome, 'resolved');
  assert.equal(draft({ ...ticket(), events: [reply, sent] }).outcome, '');
  const request = draft({ ...ticket(), events: [{ kind: 'sent', purpose: 'request' }] });
  assert.ok(request.action.includes('추가정보 요청')); assert.ok(!request.action.includes('고객 답변'));
});
