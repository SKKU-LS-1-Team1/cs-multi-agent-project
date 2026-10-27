import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

const exports = {};
vm.runInNewContext(ts.transpileModule(fs.readFileSync(new URL('../src/admin/lib/send-qc.ts', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText, { exports, setTimeout, clearTimeout, Error });
const { SendQcSession, checkBeforeSend } = exports;
const input = { sourceText: 'English draft', finalText: '고객 문구', language: 'ko' };
function fixture(check) {
  const states = [];
  let sent = 0;
  const session = new SendQcSession(state => states.push(state));
  const options = { input, check, isCurrent: () => true, send: async () => { sent++; return true; }, timeoutMs: 100 };
  return { session, options, states, get sent() { return sent; } };
}
test('pass checks both texts before sending', async () => {
  const f = fixture(async received => { assert.deepEqual({ ...received }, input); return { status: 'passed' }; });
  await f.session.run(f.options);
  assert.equal(f.sent, 1);
  assert.deepEqual(f.states.map(s => s.phase), ['checking', 'sending', 'sent']);
});
test('abuse and confidentiality violations block send and retain evidence', async () => {
  for (const category of ['abuse', 'confidential']) {
    const issues = [{ category, excerpt: 'offending passage', reason: '수정 필요' }];
    const f = fixture(async () => ({ status: 'blocked', issues }));
    await f.session.run(f.options);
    assert.equal(f.sent, 0);
    assert.equal(f.states.at(-1).phase, 'blocked');
    assert.equal(f.states.at(-1).issues, issues);
  }
});
test('unconnected live QC never sends', async () => {
  const f = fixture(value => checkBeforeSend(value, false));
  await f.session.run(f.options);
  assert.equal(f.sent, 0);
  assert.match(f.states.at(-1).message, /연결되지/);
});
test('timeout prevents late send; explicit retry works', async () => {
  let resolve;
  const f = fixture(() => new Promise(r => { resolve = r; }));
  await f.session.run({ ...f.options, timeoutMs: 5 });
  assert.equal(f.states.at(-1).phase, 'error');
  resolve({ status: 'passed' });
  await Promise.resolve();
  assert.equal(f.sent, 0);
  await f.session.run({ ...f.options, check: async () => ({ status: 'passed' }) });
  assert.equal(f.sent, 1);
});
test('duplicate clicks cannot duplicate checks or sends', async () => {
  let resolve, calls = 0;
  const f = fixture(() => { calls++; return new Promise(r => { resolve = r; }); });
  const first = f.session.run(f.options);
  await f.session.run(f.options);
  resolve({ status: 'passed' });
  await first;
  assert.equal(calls, 1);
  assert.equal(f.sent, 1);
});
test('changed content invalidates a QC pass', async () => {
  const f = fixture(async () => ({ status: 'passed' }));
  await f.session.run({ ...f.options, isCurrent: () => false });
  assert.equal(f.sent, 0);
  assert.match(f.states.at(-1).message, /변경/);
});
test('unmount cancels pending send', async () => {
  let resolve;
  const f = fixture(() => new Promise(r => { resolve = r; }));
  const pending = f.session.run(f.options);
  f.session.cancel();
  resolve({ status: 'passed' });
  await pending;
  assert.equal(f.sent, 0);
  assert.deepEqual(f.states.map(s => s.phase), ['checking']);
});
test('malformed results cannot authorize send', async () => {
  for (const result of [null, {}, { status: 'blocked', issues: [] }]) {
    const f = fixture(async () => result);
    await f.session.run(f.options);
    assert.equal(f.sent, 0);
    assert.equal(f.states.at(-1).phase, 'error');
  }
});

test('failed send never displays completion', async () => {
  const f = fixture(async () => ({ status: 'passed' }));
  await f.session.run({ ...f.options, send: async () => false });
  assert.equal(f.states.at(-1).phase, 'error');
  assert.ok(!f.states.some(s => s.phase === 'sent'));
});
test('successful send cannot be repeated from completion state', async () => {
  const f = fixture(async () => ({ status: 'passed' }));
  await f.session.run(f.options);
  await f.session.run(f.options);
  assert.equal(f.sent, 1);
});

test('server owns QC and completion; one combined request', async () => {
  const states = [];
  const session = new SendQcSession(s => states.push(s));
  let calls = 0;
  await session.runServer(async () => { calls++; return { sent: true, qc: { decision: 'PASS', issues: [] } }; });
  await session.runServer(async () => { calls++; });
  assert.equal(calls, 1);
  assert.deepEqual(states.map(s => s.phase), ['checking', 'sent']);
});
test('server BLOCK/REVIEW show safe locations and do not offer override', async () => {
  for (const decision of ['BLOCK', 'REVIEW']) {
    const states = [];
    const session = new SendQcSession(s => states.push(s));
    await session.runServer(async () => ({ sent: false, qc: { decision, issues: [
      { paragraph_id: 'p2', category: 'CREDENTIAL', reason: '인증정보', suggestion: '삭제', source_id: null },
    ] } }));
    assert.equal(states.at(-1).phase, 'blocked');
    assert.match(states.at(-1).issues[0].excerpt, /2번 문단/);
    assert.ok(!states.some(s => s.phase === 'sent'));
  }
});
test('server error, missing QC, and transport failure never show completion', async () => {
  for (const submit of [
    async () => ({ sent: false, qc: { decision: 'ERROR', message: '검증 실패' } }),
    async () => ({ sent: true }),
    async () => { throw Error('network'); },
  ]) {
    const states = [];
    await new SendQcSession(s => states.push(s)).runServer(submit);
    assert.equal(states.at(-1).phase, 'error');
    assert.ok(!states.some(s => s.phase === 'sent'));
  }
});
test('pending server request suppresses duplicate submit', async () => {
  let finish, calls = 0;
  const states = [];
  const session = new SendQcSession(s => states.push(s));
  const submit = () => { calls++; return new Promise(r => { finish = r; }); };
  const first = session.runServer(submit);
  await session.runServer(submit);
  finish({ sent: true, qc: { decision: 'PASS', issues: [] } });
  await first;
  assert.equal(calls, 1);
});
