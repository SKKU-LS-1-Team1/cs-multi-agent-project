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
    './api-sync': { isApiTicket: t => t.source === 'api', resolveViaApi: async (t, body) => {
      state.calls++; state.resolveInput = body;
      const ok = await state.resolve(t);
      if (ok) { t.resolution = { ...body, confirmedBy: body.confirmed_by, confirmedAt: '2026-10-23T12:00:00Z' };
        t.events.push({ kind: 'completed', source: 'resolution-api', resolution: t.resolution }); }
      return ok;
    } },
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

function apiFixture() {
  const calls = [], state = { reply: null, fail: false, release: null, commits: 0 };
  const logic = {
    people: [], signedIn: 'tester', contextKey: c => JSON.stringify(c),
    answerContext: t => ({ references: [], specialistRevision: t.specialistRevision }),
    waitingReviews: t => t.events.filter(e => e.kind === 'escalation' && !t.events.some(r => r.requestId === e.id)),
    record: (t, kind, text, extra) => t.events.push({ kind, text, ...extra }),
  };
  const call = name => async (...args) => {
    calls.push({ name, args });
    if (state.fail) throw new Error('network');
    if (state.release) return new Promise(resolve => { state.release(resolve); });
    return state.reply;
  };
  const mod = load('lib/api-sync.ts', {
    sonner: { toast }, '../../api/client': { api: {
      replyPreview: call('preview'), manualReply: call('manual-reply'), specialistRequest: call('request'), specialistReply: call('reply'), act: call('act'), resolve: call('resolve'), informationReview: call('information-review'),
    } }, './logic': logic, './store': { commit: () => state.commits++, openModal: noop, setUi: noop, tickets: [] },
  });
  return { mod, calls, state };
}
function setPreview(mod, t) {
  t.replyPreview = { preview_id: 'preview-1', source_text: t.draft, final_text: 'Prepared customer text' };
  t.replyPreviewKey = mod.replyPreviewKey(t);
}
function apiRow(overrides = {}) {
  return { ticket_id: 'T-X', inquiry: { subject: 'Fault', body: 'motor stopped', language: 'en' },
    status: 'READY_FOR_REVIEW', draft: { text: 'Initial draft', cited: [] }, info_request: null,
    checks: [], evidence: [], specialist_requests: [], specialist_revision: 0, draft_specialist_revision: 0,
    ...overrides };
}
const requestRow = (id = 'req-1', reply = null) => ({ request_id: id, text: 'Please check', to_dept: 'TS_AUTO',
  requested_by: 'Tester', created_at: '2026-10-23T10:00:00Z', channel: '이메일', attachment_names: ['log.csv'], reply });
const specialistReply = { reply_id: 'rep-1', text: 'Check wiring', author: 'Engineering', created_at: '2026-10-23T11:00:00Z' };

test('specialist polling restores history once and preserves edited draft while invalidating review', () => {
  const { mod } = apiFixture(); const t = mod.apply(undefined, apiRow());
  t.draft = 'My edited draft'; t.reviewed = true;
  const row = apiRow({ specialist_requests: [requestRow('req-1', specialistReply)], specialist_revision: 2 });
  mod.apply(t, row); mod.apply(t, row);
  assert.equal(t.events.filter(e => e.kind === 'escalation').length, 1);
  assert.equal(t.events.filter(e => e.kind === 'expert').length, 1);
  assert.equal(t.events.find(e => e.kind === 'expert').requestId, 'req-1');
  assert.equal(t.events.find(e => e.kind === 'escalation').transmittedFiles[0], 'log.csv');
  assert.equal(t.draft, 'My edited draft'); assert.equal(t.reviewed, false);
  assert.equal(mod.specialistDraftStale(t), true);
  mod.apply(t, apiRow()); // stale poll started before the reply was saved
  assert.equal(t.specialistRevision, 2); assert.equal(t.draft, 'My edited draft');
});
test('request retry reuses its ID after lost response and duplicate clicks are ignored', async () => {
  const { mod, state, calls } = apiFixture(); const t = mod.apply(undefined, apiRow());
  const input = { department: '자동화 기술지원', body: 'Check wiring', channel: '이메일', files: ['log.csv'] };
  state.fail = true;
  assert.equal(await mod.specialistRequestViaApi(t, input), false);
  const id = calls[0].args[1].request_id;
  assert.ok(t.pendingSpecialistRequest); assert.equal(t.events.filter(e => e.kind === 'escalation').length, 0);
  state.fail = false; let release;
  state.release = resolve => { release = resolve; };
  const pending = mod.specialistRequestViaApi(t, input);
  assert.equal(await mod.specialistRequestViaApi(t, input), false);
  assert.equal(calls.length, 2); assert.equal(calls[1].args[1].request_id, id);
  assert.equal(calls[1].args[1].to_dept, 'TS_AUTO');
  release(apiRow({ specialist_requests: [requestRow(id)], specialist_revision: 1 }));
  assert.equal(await pending, true); assert.equal(t.pendingSpecialistRequest, undefined);
  assert.equal(t.specialistSaving, false);
});
test('reply retry uses the same ID and does not fabricate success events on failure', async () => {
  const { mod, state, calls } = apiFixture();
  const t = mod.apply(undefined, apiRow({ specialist_requests: [requestRow()], specialist_revision: 1 }));
  state.fail = true;
  assert.equal(await mod.specialistReplyViaApi(t, 'req-1', 'Check wiring'), false);
  assert.equal(t.events.some(e => e.kind === 'expert'), false);
  const id = calls[0].args[2].reply_id;
  state.fail = false;
  state.reply = apiRow({ specialist_requests: [requestRow('req-1', { ...specialistReply, reply_id: id })], specialist_revision: 2 });
  assert.equal(await mod.specialistReplyViaApi(t, 'req-1', 'Check wiring'), true);
  assert.equal(calls[1].args[2].reply_id, id); assert.equal(t.events.filter(e => e.kind === 'expert').length, 1);
});
test('stale and pending specialist drafts cannot be sent; fresh approval includes expected revision', async () => {
  const { mod, state, calls } = apiFixture();
  const t = mod.apply(undefined, apiRow({ specialist_requests: [requestRow()], specialist_revision: 1 }));
  t.purpose = 'answer'; assert.equal(await mod.sendViaApi(t), false); assert.equal(calls.length, 0);
  mod.apply(t, apiRow({ specialist_requests: [requestRow('req-1', specialistReply)], specialist_revision: 2 }));
  assert.equal(await mod.sendViaApi(t), false); assert.equal(calls.length, 0);
  t.draftSpecialistRevision = 2;
  state.reply = apiRow({ status: 'APPROVED', final_reply: 'Sent answer', specialist_revision: 2, draft_specialist_revision: 2 });
  setPreview(mod, t);
  assert.equal(await mod.sendViaApi(t), true);
  assert.equal(calls[0].args[1].expected_specialist_revision, 2);
});
test('rewrite uses new specialist reply, preserves old text in history and records new cited revision', async () => {
  const { mod, state, calls } = apiFixture();
  const t = mod.apply(undefined, apiRow({ specialist_requests: [requestRow('req-1', specialistReply)], specialist_revision: 2 }));
  t.draft = 'My edited draft';
  state.reply = apiRow({ specialist_revision: 2, draft_specialist_revision: 2,
    specialist_requests: [requestRow('req-1', specialistReply)], draft: { text: 'New answer', cited: ['specialist:rep-1'] } });
  assert.equal(await mod.rewriteViaApi(t, 'Use the specialist reply'), true);
  assert.equal(calls[0].args[1].action, 'rewrite'); assert.equal(t.draft, 'New answer');
  assert.equal(t.draftCited[0], 'specialist:rep-1'); assert.equal(t.draftSpecialistRevision, 2);
  assert.ok(t.events.some(e => e.kind === 'draft-replaced' && e.draft === 'My edited draft'));
});
test('failed rewrite with HTTP success/ON_HOLD keeps editor even through a later poll', async () => {
  const { mod, state } = apiFixture();
  const t = mod.apply(undefined, apiRow());
  state.reply = apiRow({ status: 'ON_HOLD', draft: null });
  assert.equal(await mod.rewriteViaApi(t, 'rewrite'), false);
  assert.equal(t.draft, 'Initial draft');
  mod.apply(t, state.reply); assert.equal(t.draft, 'Initial draft'); assert.equal(t.regenerating, false);
});
test('edits made during rewrite survive and new AI draft is offered separately', async () => {
  const { mod, state } = apiFixture(); const t = mod.apply(undefined, apiRow()); let release;
  state.release = resolve => { release = resolve; };
  const pending = mod.rewriteViaApi(t, 'rewrite'); t.draft = 'Typed during request';
  release(apiRow({ draft: { text: 'New answer', cited: [] } }));
  assert.equal(await pending, true); assert.equal(t.draft, 'Typed during request');
  assert.equal(t.pendingAnswer.draft, 'New answer');
});

test('Copilot keeps all server replies and only labels actually cited replies as used', () => {
  const logic = load('lib/logic.ts', {
    '@admin/data/knowledge-data': { caseCatalog: [] },
    './auth': { currentAccount: () => undefined, ACCOUNTS: [
      { userId: '1', name: 'Doyeon Kim', role: 'LEAD' }, { userId: '2', name: 'Minji Park' },
      { userId: '3', name: 'Jun Lee' }, { userId: '4', name: 'Hana Choi' },
    ] }, './store': { tickets: [], onBeforeCommit: noop, save: noop },
  });
  const t = { ...ticket(), product: 'iS7', events: [
    { kind: 'escalation', id: 'r1', department: 'QA', source: 'specialist-api' },
    { kind: 'expert', id: 'e1', requestId: 'r1', text: 'first', source: 'specialist-api' },
    { kind: 'escalation', id: 'r2', department: 'Tech', source: 'specialist-api' },
    { kind: 'expert', id: 'e2', requestId: 'r2', text: 'second', source: 'specialist-api' },
  ], draftCited: ['specialist:e1'] };
  const c = logic.answerContext(t);
  assert.equal(c.expertReferences.length, 2); assert.equal(c.references.length, 1);
  assert.equal(c.references[0].text, 'first'); assert.equal(c.references[0].label, 'QA 검토 회신');
});

test('poll clears saved busy flags after reload without losing a manually edited draft', () => {
  const { mod } = apiFixture(); const t = mod.apply(undefined, apiRow());
  t.regenerating = true; t.specialistSaving = true; t.draft = 'Saved edit';
  mod.apply(t, apiRow());
  assert.equal(t.regenerating, false); assert.equal(t.specialistSaving, false);
  assert.equal(t.draft, 'Saved edit');
});

test('poll started before rewrite completion cannot replace the new draft with old text', async () => {
  let release; const rows = []; let started;
  const reached = new Promise(resolve => { started = resolve; });
  const mod = load('lib/api-sync.ts', {
    sonner: { toast }, '../../api/client': { api: {
      workList: async () => [{ ticket_id: 'T-X' }], agents: async () => [], answered: async () => [], closed: async () => [],
      ticket: async () => new Promise(resolve => { release = resolve; started(); }),
    } },
    './logic': { people: [], contextKey: c => JSON.stringify(c), answerContext: () => ({ references: [] }), signedIn: 'tester' },
    './store': { tickets: rows, commit: noop, setUi: noop },
  });
  const t = mod.apply(undefined, apiRow()); rows.push(t);
  const poll = mod.syncFromApi(); await reached;
  mod.apply(t, apiRow({ draft: { text: 'New draft', cited: [] } }));
  release(apiRow()); await poll;
  assert.equal(t.draft, 'New draft');
});

test('edited approval sends exact text and acknowledgment without optional feedback; one sent event', async () => {
  const { mod, state, calls } = apiFixture(); const t = mod.apply(undefined, apiRow());
  t.draft = '  Exact staff wording\n'; t.purpose = 'answer';
  state.reply = apiRow({ status: 'APPROVED', final_reply: 'Customer translation', final_reply_language: 'fr' });
  setPreview(mod, t);
  assert.equal(await mod.sendViaApi(t, { acknowledgedFailures: true }), true);
  const sent = calls[0].args[1];
  assert.equal(sent.action, 'edit_approve'); assert.equal(sent.edited_text, '  Exact staff wording\n');
  assert.equal('feedback_reason' in sent, false); assert.equal('feedback' in sent, false);
  assert.equal(sent.acknowledged_failures, true); assert.equal(sent.reviewer, 'tester');
  assert.equal(t.events.filter(e => e.kind === 'sent').length, 1);
  assert.equal(t.events.find(e => e.kind === 'sent').masterText, '  Exact staff wording\n');
  assert.equal(t.sendFeedback, undefined);
});
test('validation HOLD is not a send: candidate remains and new checks are displayed', async () => {
  const { mod, state } = apiFixture(); const t = mod.apply(undefined, apiRow());
  t.draft = 'Changed unsafe claim';
  state.reply = apiRow({ status: 'ON_HOLD', approval_text: t.draft, approved_reply: t.draft,
    approval_error: 'Final check failed', final_reply: null, checks: [{ name: 'banned', passed: false, reason: 'Unsupported guarantee' }] });
  setPreview(mod, t);
  assert.equal(await mod.sendViaApi(t), false);
  assert.equal(t.draft, 'Changed unsafe claim'); assert.equal(t.sent, false);
  assert.equal(t.apiCheckedText, 'Changed unsafe claim'); assert.equal(t.apiChecks[0].passed, false);
  assert.equal(t.events.some(e => e.kind === 'sent'), false);
  assert.equal(t.sendFeedback, undefined); assert.equal(t.sending, false);
  const restored = mod.apply(undefined, state.reply);
  assert.equal(restored.draft, 'Changed unsafe claim'); assert.equal(restored.aiDraft, 'Initial draft');
});
test('HTTP failure or APPROVED without a final message cannot erase the editor or claim sent', async () => {
  const { mod, state } = apiFixture(); const t = mod.apply(undefined, apiRow());
  t.draft = 'Customer answer'; state.fail = true; setPreview(mod, t);
  assert.equal(await mod.sendViaApi(t), false); assert.equal(t.draft, 'Customer answer');
  state.fail = false; state.reply = apiRow({ status: 'APPROVED', final_reply: '' });
  assert.equal(await mod.sendViaApi(t), false); assert.equal(t.draft, 'Customer answer');
  assert.equal(t.sent, false); assert.equal(t.events.some(e => e.kind === 'sent'), false);
});
test('approval double click waits for one response', async () => {
  const { mod, state, calls } = apiFixture(); const t = mod.apply(undefined, apiRow()); let release;
  state.release = resolve => { release = resolve; };
  setPreview(mod, t);
  const pending = mod.sendViaApi(t);
  assert.equal(await mod.sendViaApi(t), false); assert.equal(calls.length, 1); assert.equal(t.sending, true);
  release(apiRow({ status: 'APPROVED', final_reply: 'Final message' }));
  assert.equal(await pending, true); assert.equal(t.sending, false);
});
function fullLogicFixture(rows = []) {
  return load('lib/logic.ts', {
    '@admin/data/knowledge-data': { caseCatalog: [] },
    './auth': { currentAccount: () => undefined, ACCOUNTS: [
      { userId: '1', name: 'Doyeon Kim', role: 'LEAD' }, { userId: '2', name: 'Minji Park' },
      { userId: '3', name: 'Jun Lee' }, { userId: '4', name: 'Hana Choi' },
    ] }, './store': { tickets: rows, onBeforeCommit: noop, save: noop },
  });
}
test('changed exact text marks checks pending; checked HOLD candidate shows actual failed checks', () => {
  const logic = fullLogicFixture(); const t = { ...ticket(), draft: 'Original', apiCheckedText: 'Original',
    apiChecks: [{ name: 'values', passed: true, reason: '' }] };
  assert.equal(logic.runChecks(t)[0].passed, true);
  t.draft = 'Original ';
  assert.equal(logic.runChecks(t)[0].pending, true);
  t.apiCheckedText = t.draft; t.apiChecks = [{ name: 'values', passed: false, reason: 'Mismatch' }];
  assert.equal(logic.runChecks(t)[0].pending, undefined); assert.equal(logic.runChecks(t)[0].passed, false);
});
test('completion sends reviewer fields and restores authoritative result after reload without duplicate events', async () => {
  const { mod, state, calls } = apiFixture(); const t = mod.apply(undefined, apiRow({ status: 'APPROVED', final_reply: 'Sent' }));
  const payload = { ...input, confirmed_by: 'tester', references: [{ id: 'specialist:r1', label: 'QA reply', kind: 'expert' }] };
  state.reply = apiRow({ status: 'RESOLVED', resolution: { ...payload, cause: 'Server-confirmed cause',
    confirmed_at: '2026-10-23T12:00:00Z', superseded: false } });
  assert.equal(await mod.resolveViaApi(t, payload), true);
  assert.equal(calls[0].name, 'resolve'); assert.equal(calls[0].args[1], payload);
  assert.equal(t.resolution.cause, 'Server-confirmed cause'); assert.equal(t.resolution.confirmedBy, 'tester');
  mod.apply(t, state.reply);
  assert.equal(t.events.filter(e => e.kind === 'completed').length, 1);
  const restored = mod.apply(undefined, state.reply);
  assert.equal(restored.resolution.confirmedAt, '2026-10-23T12:00:00Z'); assert.equal(restored.stage, 5);
});
test('unconfirmed closure and superseded result are never verified solutions', () => {
  const { mod } = apiFixture(); const rows = [];
  const resolution = { ...input, confirmed_by: 'tester', references: [], confirmed_at: '2026-10-23T12:00:00Z', superseded: false };
  const t = mod.apply(undefined, apiRow({ status: 'RESOLVED', resolution: { ...resolution, outcome: 'unconfirmed' } })); rows.push(t);
  const logic = fullLogicFixture(rows);
  assert.equal(logic.completionRecords()[0].verified, false);
  mod.apply(t, apiRow({ status: 'RESOLVED', resolution })); assert.equal(logic.completionRecords()[0].verified, true);
  mod.apply(t, apiRow({ resolution: { ...resolution, superseded: true } }));
  assert.equal(logic.completionRecords()[0].verified, false); assert.equal(logic.completionRecords()[0].superseded, true);
});
test('complete action passes all form values and leaves server confirmation authoritative', async () => {
  const { state, actions } = actionFixture(); const t = ticket();
  state.resolve = async t => { t.stage = 5; return true; };
  await actions.completeTicket(t, { ...input, outcome: 'provided' });
  assert.equal(state.resolveInput.outcome, 'provided'); assert.equal(state.resolveInput.confirmed_by, 'tester');
  assert.equal(state.resolveInput.verification, input.verification); assert.equal(state.resolveInput.action, input.action);
  assert.equal(t.resolution.confirmedAt, '2026-10-23T12:00:00Z');
});

test('checked final candidate citations replace original AI citations, including intentionally empty list', () => {
  const { mod } = apiFixture(); const logic = fullLogicFixture();
  const req = requestRow('req-1', specialistReply);
  const base = apiRow({ specialist_requests: [req], specialist_revision: 2, draft_specialist_revision: 2,
    draft: { text: 'Initial draft [specialist:rep-1]', cited: ['specialist:rep-1'] } });
  const t = mod.apply(undefined, base);
  assert.equal(logic.answerContext(t).references.length, 1);
  t.draft = 'Removed citation';
  assert.equal(logic.answerContext(t).references.length, 0);
  mod.apply(t, { ...base, status: 'ON_HOLD', approval_text: 'Removed citation', approval_cited: [] });
  assert.equal(t.draftCited.length, 0); assert.equal(logic.answerContext(t).references.length, 0);
  const final = mod.apply(undefined, { ...base, status: 'APPROVED', final_reply: 'Customer version',
    approval_text: 'Removed citation', approval_cited: [] });
  assert.equal(logic.answerContext(final).references.length, 0);
});

function analysisRow(overrides = {}) {
  return apiRow({ classification: { category: 'DEFECT', model: 'jev', confidence: 0.8 },
    extraction: { product_code: 'S100', error_code: 'E.42', fw_version: '2.10', serial_no: null,
      field_values: { current_fw: '2.10' }, field_evidence: { current_fw: 'Firmware 2.10 installed' },
      field_sources: { current_fw: 'gemini' }, provided_info: ['current_fw'], unconfirmed_fields: { serial_no: 'withdrawn' },
      unconfirmed_evidence: { serial_no: 'That is not my serial' }, issues: [], urgency: 'NONE' },
    rules: { required_info: ['current_fw', 'serial_no'], missing_info: ['serial_no'], missing_blocking: ['serial_no'] },
    field_labels: { current_fw: 'Current firmware', serial_no: 'Serial number' }, ...overrides });
}
const initialMessage = { message_id: 'initial-1', kind: 'initial', body: 'Original inquiry', subject: 'Fault', received_at: '2026-10-23T09:00:00Z', provided_fields: {} };
const customerMessage = { message_id: 'reply-1', kind: 'reply', body: 'Firmware 2.10 installed', received_at: '2026-10-23T10:00:00Z', provided_fields: {} };
const infoReview = { reply_id: 'reply-1', customer_revision: 1, reviewer: 'tester', checked_at: '2026-10-23T11:00:00Z',
  fields: { current_fw: { status: 'confirmed', value: '2.10', evidence: 'Firmware 2.10 installed' }, serial_no: { status: 'missing', evidence: '' } } };

test('actual analysis uses canonical required field IDs, values and evidence without sample fallback', () => {
  const { mod } = apiFixture(); const logic = fullLogicFixture();
  const t = mod.apply(undefined, analysisRow({ ticket_id: 'CSV1-000050' }));
  const c = logic.answerContext(t);
  assert.equal(t.analysisReady, true); assert.equal(c.analysis.errorCode, 'E.42');
  assert.equal(c.analysis.conditions.firmware, '2.10'); assert.equal(c.analysis.conditions.load, undefined);
  assert.equal(c.analysis.fieldEvidence.current_fw, 'Firmware 2.10 installed');
  assert.equal(t.infoChecks.current_fw.status, 'provided'); assert.equal(t.infoChecks.current_fw.confirmedBy, null);
  assert.equal(t.infoChecks.serial_no.status, 'unusable');
  assert.equal(logic.requiredInformation(t)[0].id, 'current_fw');
  assert.deepEqual(Array.from(c.missingInfo), ['Serial number']);
  assert.ok(!logic.inquirySummary(t).lines.join(' ').includes('E.OC'));
});
test('missing analysis is unknown, never no-additional-information and no sample field defaults', () => {
  const { mod } = apiFixture(); const logic = fullLogicFixture(); const t = mod.apply(undefined, apiRow({ ticket_id: 'CSV1-000050' }));
  t.owner = 'tester';
  assert.equal(t.analysisReady, false); assert.equal(logic.requiredInformation(t).length, 0);
  assert.equal(logic.branchChoice(t), null);
  assert.ok(logic.inquirySummary(t).lines.at(-1).includes('완료되지 않았습니다'));
});
test('customer replies and staff review restore from server once and stale reviews do not confirm newer replies', () => {
  const { mod } = apiFixture();
  const row = analysisRow({ customer_messages: [initialMessage, customerMessage], customer_revision: 1,
    draft_customer_revision: 1, information_review: infoReview, information_reviews: [infoReview] });
  const t = mod.apply(undefined, row); mod.apply(t, row);
  assert.equal(t.body, 'Original inquiry'); assert.equal(t.events.filter(e => e.source === 'customer-api').length, 1);
  assert.equal(t.reviewedReplyKey, 'reply-1'); assert.equal(t.infoChecks.current_fw.status, 'confirmed');
  assert.equal(t.infoChecks.current_fw.confirmedBy, 'tester'); assert.equal(t.customerRequestStatus, 'received');
  mod.apply(t, { ...row, customer_revision: 2, customer_messages: [initialMessage, customerMessage,
    { ...customerMessage, message_id: 'reply-2', body: 'Actually 2.20', received_at: '2026-10-23T12:00:00Z' }] });
  assert.equal(t.reviewedReplyKey, null); assert.equal(t.infoChecks.current_fw.status, 'provided');
  mod.apply(t, row); assert.equal(t.customerRevision, 2);
});
test('information review sends reply and review versions with actual values; failure does not claim saved', async () => {
  const { mod, state, calls } = apiFixture();
  const t = mod.apply(undefined, analysisRow({ customer_messages: [initialMessage, customerMessage], customer_revision: 1 }));
  state.fail = true;
  assert.equal(await mod.informationReviewViaApi(t, 'reply-1', 1, infoReview.fields, null), false);
  assert.equal(t.reviewedReplyKey, null);
  state.fail = false; state.reply = analysisRow({ customer_messages: [initialMessage, customerMessage], customer_revision: 1,
    information_review: infoReview, draft_customer_revision: 1, draft_information_reviewed_at: infoReview.checked_at });
  assert.equal(await mod.informationReviewViaApi(t, 'reply-1', 1, infoReview.fields, null), true);
  const body = calls[1].args[1];
  assert.equal(body.reply_id, 'reply-1'); assert.equal(body.customer_revision, 1); assert.equal(body.expected_reviewed_at, null);
  assert.equal(body.fields.current_fw.value, '2.10'); assert.equal(t.reviewedReplyKey, 'reply-1');
  const count = calls.length;
  assert.equal(await mod.informationReviewViaApi(t, 'reply-1', 1, infoReview.fields, null), false);
  assert.equal(calls.length, count); // stale open form can't overwrite another staff review
});
test('new customer reply and changed staff facts block old edited draft approval', async () => {
  const { mod, state, calls } = apiFixture();
  const t = mod.apply(undefined, analysisRow()); t.draft = 'Older manual draft';
  const row = analysisRow({ customer_messages: [initialMessage, customerMessage], customer_revision: 1, draft_customer_revision: 1 });
  mod.apply(t, row);
  assert.equal(t.draft, 'Older manual draft'); assert.equal(t.draftCustomerRevision, 0);
  assert.equal(await mod.sendViaApi(t), false); assert.equal(calls.length, 0);
  t.draftCustomerRevision = 1;
  mod.apply(t, { ...row, information_review: infoReview, draft_information_reviewed_at: infoReview.checked_at });
  assert.equal(await mod.sendViaApi(t), false); assert.equal(calls.length, 0);
  t.draftInformationReviewedAt = infoReview.checked_at;
  state.reply = { ...row, information_review: infoReview, status: 'APPROVED', final_reply: 'Sent', draft_information_reviewed_at: infoReview.checked_at };
  setPreview(mod, t);
  assert.equal(await mod.sendViaApi(t), true);
  assert.equal(calls[0].args[1].expected_customer_revision, 1);
  assert.equal(calls[0].args[1].expected_information_reviewed_at, infoReview.checked_at);
});
test('rewrite rejects a draft generated before the latest staff information review', async () => {
  const { mod, state } = apiFixture();
  const row = analysisRow({ customer_revision: 1, draft_customer_revision: 1, information_review: infoReview,
    draft_information_reviewed_at: infoReview.checked_at });
  const t = mod.apply(undefined, row); t.draft = 'My reviewed working draft';
  state.reply = { ...row, draft: { text: 'Stale generated answer', cited: [] }, draft_information_reviewed_at: null };
  assert.equal(await mod.rewriteViaApi(t, 'Use verified customer information'), false);
  assert.equal(t.draft, 'My reviewed working draft');
  state.reply = { ...state.reply, draft_information_reviewed_at: infoReview.checked_at };
  assert.equal(await mod.rewriteViaApi(t, 'Use verified customer information'), true);
  assert.equal(t.draft, 'Stale generated answer');
  assert.equal(t.draftInformationReviewedAt, infoReview.checked_at);
});
test('information requests send missing canonical IDs rather than display labels', async () => {
  const { mod, state, calls } = apiFixture(); const t = mod.apply(undefined, analysisRow());
  state.reply = analysisRow({ info_request: 'Please provide serial number.' });
  assert.equal(await mod.infoRequestViaApi(t), true);
  assert.deepEqual(Array.from(calls[0].args[1].info_items), ['serial_no']);
});
test('prototype event hooks cannot change server waiting/closed states', () => {
  const t = { ...ticket(), customerRequestStatus: 'waiting', events: [{ kind: 'customer', id: 'x', text: 'Older reply' }] };
  const logic = fullLogicFixture([t]); logic.synchronizeCustomerEvents();
  assert.equal(t.customerRequestStatus, 'waiting');
});
test('actual retrieved cases appear in existing context without invented cause or matching score', () => {
  const { mod } = apiFixture(); const logic = fullLogicFixture();
  const t = mod.apply(undefined, analysisRow({ evidence: [{ source: 'cases', doc_id: 'CASE-1', section: null,
    text: 'Original verified case content', metadata: { title: 'Motor support' }, score: 0.9 }],
    draft: { text: 'Answer [CASE-1]', cited: ['CASE-1'] } }));
  const c = logic.answerContext(t);
  assert.equal(c.technical.similarCases[0].text, 'Original verified case content');
  assert.equal(c.technical.similarCases[0].cause, undefined); assert.equal(c.references[0].id, 'CASE-1');
});

test('information review action waits for server success and never writes prototype status or local review', async () => {
  let release, closed = 0, calls = 0;
  const t = { ...ticket(), status: '보류', customerRevision: 1, informationReviewedAt: null,
    events: [{ kind: 'customer', id: 'reply-1', text: 'Firmware 2.10 installed' }], infoChecks: {} };
  const actions = load('lib/actions.ts', { sonner: { toast }, './logic': {
    requiredInformation: () => [{ id: 'current_fw', label: 'Current firmware' }], signedIn: 'tester',
  }, './store': { commit: noop, closeModal: () => closed++ }, './api-sync': {
    isApiTicket: () => true,
    informationReviewViaApi: async (_t, id, revision, fields, stamp) => {
      calls++; assert.equal(id, 'reply-1'); assert.equal(revision, 1); assert.equal(stamp, null);
      assert.equal(fields.current_fw.value, '2.10');
      return new Promise(resolve => { release = resolve; });
    },
  } });
  const pending = actions.saveInfoReview(t, 'reply-1', { current_fw: infoReview.fields.current_fw }, 1, null);
  assert.equal(calls, 1); assert.equal(closed, 0); assert.equal(t.status, '보류'); assert.equal(Object.keys(t.infoChecks).length, 0);
  release(false); await pending; assert.equal(closed, 0); assert.equal(t.events.length, 1);
  const retry = actions.saveInfoReview(t, 'reply-1', { current_fw: infoReview.fields.current_fw }, 1, null);
  release(true); await retry; assert.equal(closed, 1); assert.equal(t.events.length, 1); assert.equal(t.status, '보류');
});
test('API inquiry with sample ID and no evidence never gets example document, expert or case', () => {
  const { mod } = apiFixture(); const logic = fullLogicFixture();
  const t = mod.apply(undefined, analysisRow({ ticket_id: 'CSV1-000050', evidence: [], draft: { text: 'Answer', cited: [] } }));
  const c = logic.answerContext(t);
  assert.equal(c.technical.documents.length, 0); assert.equal(c.technical.similarCases.length, 0);
  assert.equal(c.expertReferences.length, 0); assert.equal(c.availableReferences.length, 0);
});
test('changing a provided field to missing or unusable does not submit its old extracted value', async () => {
  const fieldsSent = [];
  const t = { ...ticket(), customerRevision: 1, informationReviewedAt: null,
    events: [{ kind: 'customer', id: 'reply-1' }] };
  const actions = load('lib/actions.ts', { sonner: { toast }, './logic': {
    requiredInformation: () => [{ id: 'current_fw', label: 'Current firmware' }], signedIn: 'tester',
  }, './store': { commit: noop, closeModal: noop }, './api-sync': {
    isApiTicket: () => true,
    informationReviewViaApi: async (_t, _id, _revision, fields) => { fieldsSent.push(fields); return true; },
  } });
  for (const status of ['missing', 'unusable']) {
    await actions.saveInfoReview(t, 'reply-1', { current_fw: { status, value: '2.10', evidence: 'Firmware value withdrawn' } }, 1, null);
  }
  assert.equal(fieldsSent.length, 2);
  for (const fields of fieldsSent) { assert.equal(fields.current_fw.value, undefined); assert.equal(fields.current_fw.evidence, 'Firmware value withdrawn'); }
});

function noticeFixture() {
  const calls = [], state = { response: null, fail: false, deferred: null, error: null };
  const call = name => async (...args) => {
    calls.push({ name, args });
    if (state.error) throw state.error;
    if (state.fail) throw new Error('503 unavailable');
    if (state.deferred) return new Promise(resolve => { state.deferred(resolve); });
    return state.response;
  };
  const mod = load('lib/progress-notice.ts', { '../../api/client': { api: {
    progressNotices: call('list'), progressNotice: call('generate'), prepareProgressNotice: call('prepare'),
  } } });
  const session = new mod.NoticeSession(noop); session.select(['T-1']);
  return { mod, session, state, calls };
}
const noticeRow = (overrides = {}) => ({ notice_id: 'notice-1', anchor_ticket_id: 'T-1', ticket_ids: ['T-1'],
  customer_id: 'C-1', target_language: 'fr', status: 'draft', draft_text: 'Your request is under review.', approved_text: null,
  final_text: null, reviewer: null, created_at: '2026-10-23T12:00:00Z', approved_at: null, error: null, source_facts: [], ...overrides });

test('progress notices only select real server tickets for the exact customer', () => {
  const { mod } = noticeFixture();
  const actual = { id: 'T-1', source: 'api', apiCustomerId: 'C-1' };
  const rows = mod.noticeTickets('C-1', [actual, { ...actual, source: 'local' }, { ...actual, apiCustomerId: 'C-2' }, { id: 'CSV1-000050' }]);
  assert.equal(rows.length, 1); assert.equal(rows[0], actual);
});
test('notice restore picks latest exact ticket set and retains prepared English and customer text', async () => {
  const { mod, session, state } = noticeFixture();
  state.response = [noticeRow({ notice_id: 'old', created_at: '2026-10-22T12:00:00Z' }),
    noticeRow({ status: 'prepared', approved_text: 'Approved English', final_text: 'Texte français' }),
    noticeRow({ ticket_ids: ['T-2'], created_at: '2026-10-24T12:00:00Z' })];
  await session.restore();
  assert.equal(session.state.text, 'Approved English'); assert.equal(mod.preparedNotice(session.state).final_text, 'Texte français');
});
test('notice generation retries use one UUID and duplicate clicks do not create duplicate requests', async () => {
  const { session, state, calls } = noticeFixture(); state.fail = true;
  session.edit('My existing edit');
  assert.equal(await session.generate(), false); assert.equal(session.state.text, 'My existing edit');
  const id = calls[0].args[1].notice_id;
  let release; state.fail = false; state.deferred = resolve => { release = resolve; };
  const pending = session.generate(); assert.equal(await session.generate(), false); assert.equal(calls.length, 2);
  release(noticeRow({ notice_id: id })); assert.equal(await pending, true);
  assert.equal(calls[1].args[1].notice_id, id); assert.equal(session.state.text, 'Your request is under review.');
});
test('late generated notices cannot overwrite changed selection or staff input', async () => {
  const { session, state } = noticeFixture(); let release;
  state.deferred = resolve => { release = resolve; };
  let pending = session.generate(); session.select(['T-2']); release(noticeRow());
  assert.equal(await pending, false); assert.equal(session.state.text, ''); assert.equal(session.state.notice, null);
  session.select(['T-1']); pending = session.generate(); session.edit('Staff typed while AI was writing'); release(noticeRow());
  assert.equal(await pending, true); assert.equal(session.state.text, 'Staff typed while AI was writing');
  assert.equal(session.state.notice.draft_text, 'Your request is under review.');
});
test('notice prepare sends exact English edit and reviewer and never treats failed conversion as prepared', async () => {
  const { mod, session, state, calls } = noticeFixture(); state.response = noticeRow(); await session.generate();
  const edited = '  Exact edited text\nSecond line  '; session.edit(edited);
  state.response = noticeRow({ error: 'translation_failed' });
  assert.equal(await session.prepare('reviewer'), null); assert.equal(session.state.text, edited);
  assert.equal(mod.preparedNotice(session.state), null); assert.equal(calls.at(-1).args[2].edited_text, edited);
  state.response = noticeRow({ status: 'prepared', approved_text: edited, final_text: 'Texte final', reviewer: 'reviewer' });
  assert.equal((await session.prepare('reviewer')).final_text, 'Texte final');
  assert.equal(calls.at(-1).args[2].reviewer, 'reviewer'); assert.equal(session.state.text, edited);
  assert.ok(calls.every(c => ['generate', 'prepare'].includes(c.name))); // no action/send endpoint
});
test('notice approval and restore responses never overwrite edits made while awaiting network', async () => {
  const { mod, session, state } = noticeFixture(); state.response = noticeRow(); await session.generate(); let release;
  state.deferred = resolve => { release = resolve; };
  const approval = session.prepare('reviewer'); session.edit('New edit');
  release(noticeRow({ status: 'prepared', approved_text: 'Your request is under review.', final_text: 'Old French' }));
  assert.equal(await approval, null); assert.equal(session.state.text, 'New edit'); assert.equal(mod.preparedNotice(session.state), null);
  const restore = session.restore(); session.edit('Latest typing'); release([noticeRow()]); await restore;
  assert.equal(session.state.text, 'Latest typing');
});
test('prepared notice local reference stores both versions once without acting or sending', () => {
  const disk = new Map();
  const care = load('lib/care.ts', { react: { useSyncExternalStore: noop }, './logic': { signedIn: 'reviewer' } },
    { localStorage: { getItem: k => disk.get(k) ?? null, setItem: (k, v) => disk.set(k, v) } });
  const row = noticeRow({ status: 'prepared', approved_text: 'Approved English', final_text: 'French version', reviewer: 'reviewer', approved_at: '2026-10-23T12:05:00Z' });
  care.rememberProgressNotice(row); care.rememberProgressNotice(row);
  const r = care.recordOf('C-1'); assert.equal(r.actions.length, 1); assert.equal(care.careStatus(r), 'none');
  assert.equal(r.actions[0].originalText, 'Approved English'); assert.equal(r.actions[0].finalText, 'French version');
  assert.equal(r.actions[0].kind, 'notice_draft'); assert.equal(r.followUp, undefined); assert.equal(r.resolved, undefined);
});
test('same selected tickets always use canonical anchor so saved notices reopen regardless of click order', async () => {
  const { session, state, calls } = noticeFixture(); session.select(['T-2', 'T-1']);
  state.response = []; await session.restore(); assert.equal(calls[0].args[0], 'T-1');
  state.response = noticeRow({ ticket_ids: ['T-1', 'T-2'] }); await session.generate();
  assert.equal(calls[1].args[0], 'T-1'); assert.deepEqual(Array.from(calls[1].args[1].ticket_ids), ['T-1', 'T-2']);
});
test('known stale notice conflict gets a fresh ID on explicit retry while preserving the staff draft', async () => {
  const { session, state, calls } = noticeFixture();
  session.edit('Staff working text'); state.error = new Error('409 source facts changed');
  assert.equal(await session.generate(), false); assert.equal(session.state.text, 'Staff working text');
  const rejectedId = calls[0].args[1].notice_id;
  state.error = null; state.response = noticeRow();
  assert.equal(await session.generate(), true);
  assert.notEqual(calls[1].args[1].notice_id, rejectedId);
});


test('explicit conversion does not send and source edits invalidate its preview', async () => {
  const { mod, state, calls } = apiFixture(); const t = mod.apply(undefined, apiRow());
  assert.equal(await mod.sendViaApi(t), false); assert.equal(calls.length, 0);
  state.reply = { preview_id: 'p1', source_text: t.draft, target_language: 'fr', final_text: 'Bonjour' };
  assert.equal(await mod.prepareReplyViaApi(t), true);
  assert.equal(calls[0].name, 'preview'); assert.equal(t.sent, false);
  assert.equal(mod.hasCurrentReplyPreview(t), true);
  t.draft += ' changed';
  assert.equal(mod.hasCurrentReplyPreview(t), false);
  assert.equal(await mod.sendViaApi(t), false); assert.equal(calls.length, 1);
});
test('conversion response cannot overwrite a source edited while translating', async () => {
  const { mod, state, calls } = apiFixture(); const t = mod.apply(undefined, apiRow()); let release;
  state.release = resolve => { release = resolve; };
  const pending = mod.prepareReplyViaApi(t);
  assert.equal(await mod.prepareReplyViaApi(t), false); assert.equal(calls.length, 1);
  t.draft = 'New staff wording';
  release({ preview_id: 'p-old', final_text: 'Old translation' });
  assert.equal(await pending, false); assert.equal(mod.hasCurrentReplyPreview(t), false);
  assert.equal(t.translatingReply, false);
});
test('new customer context invalidates a prepared translation', () => {
  const { mod } = apiFixture(); const t = mod.apply(undefined, apiRow());
  setPreview(mod, t); assert.equal(mod.hasCurrentReplyPreview(t), true);
  t.customerRevision = 1; assert.equal(mod.hasCurrentReplyPreview(t), false);
});


test('reverting a failed staff edit sends the exact restored source rather than the old failed text', async () => {
  const { mod, state, calls } = apiFixture();
  const t = mod.apply(undefined, apiRow({ status: 'ON_HOLD', approval_text: 'Old failed staff edit' }));
  t.draft = t.aiDraft; setPreview(mod, t);
  state.reply = apiRow({ status: 'APPROVED', final_reply: 'Prepared customer text' });
  assert.equal(await mod.sendViaApi(t), true);
  assert.equal(calls[0].args[1].action, 'edit_approve');
  assert.equal(calls[0].args[1].edited_text, 'Initial draft');
  assert.equal(calls[0].args[1].reply_preview_id, 'preview-1');
});
test('reload clears stale translating state but an active request survives polling', async () => {
  const { mod, state } = apiFixture(); const t = mod.apply(undefined, apiRow());
  t.translatingReply = true;
  mod.apply(t, apiRow()); assert.equal(t.translatingReply, false);
  let release; state.release = resolve => { release = resolve; };
  const pending = mod.prepareReplyViaApi(t);
  mod.apply(t, apiRow()); assert.equal(t.translatingReply, true);
  release({ preview_id: 'p1', source_text: t.draft, final_text: 'Prepared customer text' });
  assert.equal(await pending, true); assert.equal(t.translatingReply, false);
});

test('server timeline restores multiple sent replies and assignments without local duplicates', () => {
  const { mod } = apiFixture();
  const row = apiRow({ processing_history: [
    { id: 'sent-1', kind: 'sent', created_at: '2026-10-21T10:00:00Z', actor: 'Staff A', text: 'First request', purpose: 'request', master_text: 'English request' },
    { id: 'sent-2', kind: 'sent', created_at: '2026-10-22T10:00:00Z', actor: 'Staff B', text: 'Final answer', purpose: 'answer', master_text: 'English answer' },
  ], assignment_history: [{ from_assignee: null, to_assignee: 'A-1', reason: 'Auto assign', assigned_by: '', created_at: '2026-10-20T10:00:00Z' }] });
  const t = mod.apply(undefined, row);
  t.events.push({ kind: 'sent', text: 'Final answer' }, { kind: 'assignment', text: 'Old local assignment' });
  mod.apply(t, row); mod.apply(t, row);
  assert.equal(t.events.filter(e => e.kind === 'sent').length, 2);
  assert.equal(t.events.filter(e => e.kind === 'assignment').length, 1);
  assert.equal(t.events.find(e => e.id === 'sent-1').masterText, 'English request');
  assert.equal(t.events.find(e => e.id === 'sent-2').actor, 'Staff B');
});
test('new session loads closed tickets from the server and preserves actual completion wording', async () => {
  const rows = [];
  const mod = load('lib/api-sync.ts', {
    sonner: { toast }, '../../api/client': { api: {
      workList: async () => [], agents: async () => [], answered: async () => [], closed: async () => ['T-CLOSED'],
      ticket: async id => apiRow({ ticket_id: id, status: 'RESOLVED', final_reply: 'Answer', processing_history: [], assignment_history: [] }),
    } }, './logic': { people: [], answerContext: () => ({}), contextKey: JSON.stringify },
    './store': { tickets: rows, commit: noop, setUi: noop },
  });
  assert.equal(await mod.syncFromApi(), true);
  assert.equal(rows.length, 1); assert.equal(rows[0].id, 'T-CLOSED');
  assert.equal(rows[0].stage, 5); assert.equal(rows[0].sla, '완료');
});
test('manual human reply uses the existing editor and is saved before conversion', async () => {
  const { mod, state, calls } = apiFixture();
  const t = mod.apply(undefined, apiRow({ status: 'HUMAN_QUEUE', draft: null }));
  mod.restoreAiDraft(t);
  assert.equal(t.composerOpen, true); assert.equal(t.activeComposer, 'customer'); assert.equal(t.draft, '');
  mod.apply(t, apiRow({ status: 'HUMAN_QUEUE', draft: null }));
  assert.equal(t.composerOpen, true);
  t.draft = 'Staff writes this English answer'; t.reviewed = true;
  let release;
  state.release = resolve => { release = resolve; };
  const converting = mod.prepareReplyViaApi(t);
  assert.equal(calls[0].name, 'manual-reply');
  assert.equal(calls[0].args[1].text, t.draft);
  state.release = null;
  state.reply = { preview_id: 'manual-preview', source_text: t.draft, final_text: 'Prepared customer text' };
  release(apiRow({ status: 'ON_HOLD', manual_reply: true, draft: { text: t.draft, cited: [] } }));
  assert.equal(await converting, true);
  assert.equal(calls[1].name, 'preview'); assert.equal(t.reviewed, false);
  assert.equal(mod.hasCurrentReplyPreview(t), true);
});
test('a late manual save cannot overwrite new staff edits or trigger their translation', async () => {
  const { mod, state, calls } = apiFixture();
  const t = mod.apply(undefined, apiRow({ status: 'HUMAN_QUEUE', draft: null }));
  mod.restoreAiDraft(t); t.draft = 'First manual answer';
  let release; state.release = resolve => { release = resolve; };
  const pending = mod.prepareReplyViaApi(t);
  t.draft = 'Newer staff answer';
  release(apiRow({ status: 'ON_HOLD', manual_reply: true, draft: { text: 'First manual answer', cited: [] } }));
  assert.equal(await pending, false); assert.equal(calls.length, 1);
  assert.equal(t.draft, 'Newer staff answer'); assert.equal(mod.hasCurrentReplyPreview(t), false);
});

test('polling a saved manual draft cannot interrupt its pending conversion response', async () => {
  let releaseSave, previewCalls = 0;
  const rows = [], text = 'Staff writes this English answer';
  const saved = apiRow({ status: 'ON_HOLD', manual_reply: true, draft: { text, cited: [] } });
  const mod = load('lib/api-sync.ts', {
    sonner: { toast }, '../../api/client': { api: {
      workList: async () => [{ ticket_id: 'T-X' }], agents: async () => [], answered: async () => [], closed: async () => [],
      ticket: async () => saved,
      manualReply: async () => new Promise(resolve => { releaseSave = resolve; }),
      replyPreview: async () => { previewCalls++; return { preview_id: 'p1', source_text: text, final_text: text }; },
    } },
    './logic': { people: [], signedIn: 'tester', contextKey: JSON.stringify, answerContext: () => ({ references: [] }) },
    './store': { tickets: rows, commit: noop, setUi: noop },
  });
  const t = mod.apply(undefined, apiRow({ status: 'HUMAN_QUEUE', draft: null })); rows.push(t);
  mod.restoreAiDraft(t); t.draft = text; t.reviewed = true;
  const converting = mod.prepareReplyViaApi(t);
  // The save has reached the server, but its response is still in flight.
  assert.equal(await mod.syncFromApi(), true);
  releaseSave(saved);
  assert.equal(await converting, true);
  assert.equal(previewCalls, 1);
  assert.equal(t.reviewed, false);
  assert.equal(mod.hasCurrentReplyPreview(t), true);
});

for (const source of ['api', 'local']) {
  test(`${source} reply requires review after conversion and another conversion after editing`, async () => {
    const { mod, state, calls } = apiFixture();
    const actions = load('lib/actions.ts', {
      sonner: { toast }, './api-sync': mod,
      './store': { commit: noop },
      './logic': { contextIsNew: () => false, waitingReviews: () => [], contextKey: JSON.stringify,
        answerContext: () => ({}), needsLocalization: () => false, customerLanguage: () => 'English' },
    });
    const t = mod.apply(undefined, apiRow()); t.source = source;
    // A previously persisted check must not approve a newly converted message.
    t.reviewed = true;
    assert.equal(actions.canSend(t), false);
    state.reply = { preview_id: 'p1', source_text: t.draft, final_text: 'Prepared customer text' };
    assert.equal(await actions.prepareCustomerReply(t), true);
    assert.equal(t.reviewed, false);
    assert.equal(actions.canSend(t), false);
    actions.setReviewed(t, true);
    assert.equal(actions.canSend(t), true);
    actions.editDraft(t, 'Changed English draft');
    assert.equal(t.reviewed, false);
    assert.equal(mod.hasCurrentReplyPreview(t), false);
    assert.equal(actions.canSend(t), false);
    assert.ok(calls.every(call => call.name === 'preview')); // conversion never sends
  });
}
