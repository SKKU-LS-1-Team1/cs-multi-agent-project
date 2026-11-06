// 고객 화면 전체 번역 레이어
//
// 고객 화면(홈·상담·문의·내 문의·FAQ …)의 문구는 한국어로 코드와 data/*.json 에 들어 있다. 그 문구는
// 화면 로직(예: '제품군: ' 접두어 파싱)에도 쓰여서 키로 바꾸지 않고, 화면에 그려진 뒤 DOM 에서 바꾼다.
//
// - setPageLang(lang): 고른 언어를 적용한다. 'ko' 면 원문으로 되돌리고 번역을 멈춘다.
// - 화면에 보이는 텍스트와 placeholder · aria-label · title · alt 속성 중 한글이 들어 있는 것만 모아
//   서버 POST /api/i18n/translate 로 번역한다 (서버가 문구별로 Redis 캐시).
// - 받은 번역은 브라우저에도 저장해서(localStorage) 다시 들어오면 서버를 부르지 않고 바로 바꾼다.
// - MutationObserver 로 새로 그려진 화면·바뀐 문구도 따라가 번역한다. React 가 문구를 바꾸면
//   바뀐 값을 새 원문으로 본다.
// - 번역하지 않는 곳: translate="no" 이거나 lang="ko" 인 요소 안(언어 목록의 '한국어', 고객이 직접 쓴
//   말풍선), script · style · textarea, 입력 중인 값.
const HANGUL = /[가-힣ㄱ-ㆎ]/
const ATTRS = ['placeholder', 'aria-label', 'title', 'alt']
const SKIP_TAGS = new Set(['SCRIPT', 'STYLE', 'TEXTAREA', 'NOSCRIPT', 'CODE'])
const STORE_PREFIX = 'ls-i18n:v1:'
const STORE_MAX = 4000 // 언어당 브라우저에 남기는 문구 수
const BATCH = 60
const FIRST_PAINT_WAIT_MS = 4000 // 첫 번역을 기다리며 화면을 가리는 최대 시간

let current = 'ko'
let root = null
let observer = null
let timer = null
const texts = new Map() // Text 노드 → { src, out }
const attrs = new Map() // Element → { [attr]: { src, out } }
const caches = new Map() // lang → Map(원문 → 번역)
const queued = new Set()
// 번역을 못 받은 원문 → { n: 실패 횟수, until: 다시 물을 시각 }. 분당 호출 상한(429)·일시 오류로 한 번 실패한
// 문구가 그 방문 내내 한국어로 남지 않게, 2·4·8·16초 뒤에 다시 묻고 그래도 안 되면 이번 방문에서는 그만 묻는다.
const failed = new Map()
const MAX_TRIES = 5
let retryTimer = null

const readStore = (lang) => {
  try { return JSON.parse(localStorage.getItem(STORE_PREFIX + lang) || '{}') } catch { return {} }
}
const writeStore = (lang, map) => {
  try {
    const entries = [...map.entries()].slice(-STORE_MAX)
    localStorage.setItem(STORE_PREFIX + lang, JSON.stringify(Object.fromEntries(entries)))
  } catch { /* 저장 못 해도 이번 방문에는 메모리 캐시로 동작한다 */ }
}
const cacheOf = (lang) => {
  if (!caches.has(lang)) caches.set(lang, new Map(Object.entries(readStore(lang))))
  return caches.get(lang)
}

// 앞뒤 공백은 그대로 두고 가운데만 번역한다 (React 가 붙여 그린 문구 사이 공백 유지)
const split = (s) => {
  const m = /^(\s*)([\s\S]*?)(\s*)$/.exec(s)
  return [m[1], m[2], m[3]]
}
const lookup = (core) => cacheOf(current).get(core)

function skipped(el) {
  if (!el || el.nodeType !== 1) return true
  if (SKIP_TAGS.has(el.tagName)) return true
  if (el.closest('[translate="no"], [contenteditable="true"]')) return true
  const tagged = el.closest('[lang]')
  return !!tagged && tagged !== document.documentElement && /^ko\b/i.test(tagged.getAttribute('lang') || '')
}

function want(core) {
  if (lookup(core)) return
  const f = failed.get(core)
  if (f && (f.n >= MAX_TRIES || Date.now() < f.until)) return
  queued.add(core); schedule()
}

function doText(node) {
  const value = node.nodeValue ?? ''
  const rec = texts.get(node)
  if (rec && rec.out !== null && value === rec.out) return // 우리가 바꿔 둔 값
  if (!HANGUL.test(value) || skipped(node.parentElement)) { texts.delete(node); return }
  const [lead, core, tail] = split(value)
  const out = lookup(core)
  if (out) {
    const next = lead + out + tail
    texts.set(node, { src: value, out: next })
    node.nodeValue = next
  } else {
    texts.set(node, { src: value, out: null })
    want(core)
  }
}

function doAttr(el, name) {
  const value = el.getAttribute(name)
  const recs = attrs.get(el) ?? {}
  const rec = recs[name]
  if (rec && rec.out !== null && value === rec.out) return
  if (value === null || !HANGUL.test(value) || skipped(el)) { delete recs[name]; return }
  const core = value.trim()
  const out = lookup(core)
  recs[name] = { src: value, out: out ?? null }
  attrs.set(el, recs)
  if (out) el.setAttribute(name, out)
  else want(core)
}

function walk(node) {
  if (node.nodeType === 3) { doText(node); return }
  if (node.nodeType !== 1 || SKIP_TAGS.has(node.tagName)) return
  for (const a of ATTRS) if (node.hasAttribute(a)) doAttr(node, a)
  const w = document.createTreeWalker(node, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT)
  let n = w.nextNode()
  while (n) {
    if (n.nodeType === 3) doText(n)
    else for (const a of ATTRS) if (n.hasAttribute(a)) doAttr(n, a)
    n = w.nextNode()
  }
}

/** 받은 번역을 아직 원문인 곳에 넣는다 */
function applyPending() {
  for (const [node, rec] of texts) {
    if (!node.isConnected) { texts.delete(node); continue }
    if (rec.out === null) doText(node)
  }
  for (const [el, recs] of attrs) {
    if (!el.isConnected) { attrs.delete(el); continue }
    for (const [name, rec] of Object.entries(recs)) if (rec.out === null) doAttr(el, name)
  }
}

function restoreAll() {
  for (const [node, rec] of texts) if (node.isConnected && rec.out !== null && node.nodeValue === rec.out) node.nodeValue = rec.src
  for (const [el, recs] of attrs) {
    if (!el.isConnected) continue
    for (const [name, rec] of Object.entries(recs)) if (rec.out !== null && el.getAttribute(name) === rec.out) el.setAttribute(name, rec.src)
  }
  texts.clear(); attrs.clear()
}

let firstDone = null
let hidOnce = false // 언어마다 한 번만 가린다 (번역 서버가 계속 실패해도 화면이 거듭 사라지지 않게)
function schedule() {
  // 이 언어로 처음 들어온 방문이면 첫 번역이 올 때까지 화면을 가린다
  if (!firstDone && !hidOnce && cacheOf(current).size === 0) { hidOnce = true; hideUntilFirst() }
  if (timer) return
  timer = setTimeout(flush, 30)
}

function fail(src) {
  const n = (failed.get(src)?.n ?? 0) + 1
  const wait = 1000 * 2 ** n
  failed.set(src, { n, until: Date.now() + wait })
  scheduleRetry()
}

// 다시 물을 때가 된 문구가 생기면 화면을 다시 훑어 큐에 넣는다
function scheduleRetry() {
  if (retryTimer) return
  const now = Date.now()
  const next = Math.min(...[...failed.values()].filter((f) => f.n < MAX_TRIES && f.until > now).map((f) => f.until))
  if (!Number.isFinite(next)) return
  retryTimer = setTimeout(() => {
    retryTimer = null
    if (current === 'ko') return
    applyPending()
    scheduleRetry()
  }, Math.max(0, next - now) + 50)
}

async function flush() {
  timer = null
  const lang = current
  const batch = [...queued]
  queued.clear()
  if (lang === 'ko' || !batch.length) { firstDone?.(); return }
  const chunks = []
  for (let i = 0; i < batch.length; i += BATCH) chunks.push(batch.slice(i, i + BATCH))
  await Promise.all(chunks.map(async (chunk) => {
    try {
      const res = await fetch('/api/i18n/translate', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ lang, texts: chunk }),
      })
      if (!res.ok) throw new Error(String(res.status))
      const { translations } = await res.json()
      const cache = cacheOf(lang)
      chunk.forEach((src, i) => {
        const tr = translations?.[i]
        if (typeof tr === 'string' && tr.trim() && tr !== src) { cache.set(src, tr); failed.delete(src) }
        else fail(src)
      })
    } catch {
      chunk.forEach(fail)
    }
  }))
  writeStore(lang, cacheOf(lang))
  if (lang !== current) return // 기다리는 동안 언어가 바뀌었다
  observer?.takeRecords()
  applyPending()
  observer?.takeRecords()
  if (!queued.size) firstDone?.()
}

function onMutations(list) {
  for (const m of list) {
    if (m.type === 'characterData') doText(m.target)
    else if (m.type === 'attributes') doAttr(m.target, m.attributeName)
    else m.addedNodes.forEach(walk)
  }
}

function start() {
  root = document.body
  observer = new MutationObserver(onMutations)
  observer.observe(root, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ATTRS })
}

function stop() {
  observer?.disconnect(); observer = null
  clearTimeout(timer); timer = null
  clearTimeout(retryTimer); retryTimer = null
  queued.clear()
}

/** 첫 번역이 올 때까지 한국어가 비치지 않게 잠깐 가린다 (최대 FIRST_PAINT_WAIT_MS) */
function hideUntilFirst() {
  const html = document.documentElement
  html.classList.add('i18n-loading')
  let done = false
  const finish = () => { if (done) return; done = true; firstDone = null; html.classList.remove('i18n-loading') }
  firstDone = finish
  setTimeout(finish, FIRST_PAINT_WAIT_MS)
}

/** 화면 언어를 적용한다. 앱이 언어가 정해지거나 바뀔 때마다 부른다. */
export function setPageLang(lang) {
  const next = lang || 'ko'
  // 문서 언어만 바꾼다. 홈 화면 레이아웃은 RTL 대응이 안 돼 있어 dir 은 ltr 그대로 둔다 (글자 방향은 브라우저가 처리)
  document.documentElement.lang = next
  if (next === current && (observer || next === 'ko')) return
  stop()
  observer?.takeRecords()
  restoreAll()
  failed.clear()
  hidOnce = false
  current = next
  if (next === 'ko') { firstDone?.(); return }
  start()
  walk(document.body)
  observer.takeRecords() // 방금 우리가 바꾼 것
}

export const pageLang = () => current
