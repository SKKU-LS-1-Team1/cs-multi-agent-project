import { useCallback, useEffect, useRef, useState } from 'react'
import Header from './components/Header.jsx'
import Hero from './components/Hero.jsx'
import Footer from './components/Footer.jsx'
import RightPanel from './components/RightPanel.jsx'
import Flow from './components/Flow.jsx'
import Guide from './components/Guide.jsx'
import Info from './components/Info.jsx'
import Biz from './components/Biz.jsx'
import FaqPage from './components/FaqPage.jsx'
import Inquiries from './components/Inquiries.jsx'
import Inquire from './components/Inquire.jsx'
import Replace from './components/Replace.jsx'
import Onboarding from './components/Onboarding.jsx'
import { initialLang, loadChoice, saveChoice } from './lib/onboarding.js'
import { getProduct } from './lib/catalog.js'
import { api } from '../api/client'
import { needsReplace } from './lib/replace.js'
import { LEGACY_TOPIC } from './lib/legacy.js'
import { firmwareIntent, firmwareReply, productOfKey } from './lib/firmware.js'

export default function App() {
  const [onboarded, setOnboarded] = useState(() => { try { return sessionStorage.getItem('ls-onboarded') === '1' } catch { return false } })
  // 화면 언어: 온보딩에서 정한 값(이번 세션) → 직접 고른 값 → 브라우저·영어. 헤더에서 바꾸면 선택으로 저장한다.
  const [lang, setLang] = useState(() => {
    let s = null
    try { s = sessionStorage.getItem('ls-lang') } catch { /* 무시 */ }
    return s || loadChoice() || initialLang({ choice: null, country: null }).lang
  })
  const changeLang = (l) => { setLang(l); saveChoice(l); try { sessionStorage.setItem('ls-lang', l) } catch { /* 무시 */ } }
  // 제품 하나당 대화 하나: 카드 키(모델 코드, fam:제품군, 단종·호환 문의는 legacy:제품군)별 대화. 제품을 아직 모르면 '_' 대화.
  const [threads, setThreads] = useState({})
  const [activeKey, setActiveKey] = useState('_')
  const activeRef = useRef('_')
  const activate = (key) => { activeRef.current = key; setActiveKey(key) }
  const messages = threads[activeKey] ?? []
  const [view, setView] = useState('home')
  const viewRef = useRef(view); viewRef.current = view // 챗봇 답변이 늦게 와도 지금 화면을 보고 이동 여부를 정한다
  const [context, setContext] = useState([])
  const [nav, setNav] = useState(null) // 챗봇이 정한 화면 이동 (제품 정보)
  const [chatFocus, setChatFocus] = useState(0) // 올라갈 때마다 AI 상담 입력창에 커서를 둔다
  const [cards, setCards] = useState([]) // 상담 중인 제품 카드들 (본 제품이 쌓인다. 최근 것이 위)
  const [dismissed, setDismissed] = useState(null) // 지운 카드의 키 — 같은 제품을 계속 보는 동안 다시 만들지 않는다
  const epoch = useRef(0) // 대화 초기화 때마다 올라간다 — 초기화 전에 요청한 답변은 버린다
  const sessions = useRef({}) // 대화(thread) 키 → 서버 챗봇 세션. 대화가 다른 키로 옮겨 가면 세션도 같이 옮긴다
  const [draft, setDraft] = useState(null)
  const [submitted, setSubmitted] = useState([])
  const [openMine, setOpenMine] = useState(null)
  const exit = () => { setView('home'); setContext([]); setNav(null) }

  const [replace, setReplace] = useState(null) // 대체 모델 비교·추천 화면을 연 제품군과 돌아갈 화면 { family, from }
  const openInquiry = (d = {}) => {
    // 단종·호환·대체 문의는 먼저 대체 모델 비교·추천 화면을 거친다. 그 화면의 "추천 없이 문의"(direct)는 문의서로 바로 간다.
    if (needsReplace(d)) { setReplace({ family: d.family, from: view }); setView('replace'); return }
    setDraft(d); setView('inquire')
  }
  const chatDraft = () => {
    const user = messages.filter((m) => m.role === 'user').map((m) => m.content)
    const code = getProduct(activeKey) ? activeKey : activeKey === '_' ? context.map((l) => l.match(/\(([A-Za-z0-9-]+)\)\s*$/)?.[1]).find((c) => c && getProduct(c)) : null
    const p = code ? getProduct(code) : null
    const asked = messages.filter((m) => m.role === 'assistant' && m.kind !== 'handoff').map((m) => m.content)
    const picked = messages.filter((m) => m.kind === 'handoff').flatMap((m) => m.lines) // 해결 화면에서 이어 온 선택·해 본 조치
    const symptom = picked.find((l) => l.startsWith('증상: '))?.slice(4)
    openInquiry({
      family: p?.family, model: p?.code, subject: (user[0] ?? symptom ?? '').split('\n')[0].slice(0, 100),
      body: `${user.length ? `고객 메시지:\n${user.map((x) => `- ${x}`).join('\n')}` : ''}${picked.length ? `${user.length ? '\n\n' : ''}선택한 내용 · 해 본 조치:\n${picked.map((x) => `- ${x}`).join('\n')}` : ''}${asked.length ? `\n\n챗봇에서 이미 안내받은 조치:\n${asked.map((x) => `- ${x}`).join('\n')}` : ''}`,
      chat: { messages: messages.map(({ role, content }) => ({ role, content })), docs: [] },
    })
  }
  const again = (t) => openInquiry({
    type: t.category_code || undefined, family: t.product_family, model: t.product_code || undefined, fromTicket: t.ticket_id,
    subject: `[재문의] ${t.inquiry_subject || ''}`.trim().slice(0, 100), body: `이전 문의 ${t.ticket_id}와 같은 문제로 다시 문의해요.\n`,
  })

  // 화면이 알려 주는 제품·모델로 "상담 중인 제품" 카드를 쌓는다 (모델을 알면 모델 기준, 아직 제품군만 알면 제품군 기준)
  // 단종·호환 문의는 같은 제품군의 모델 상담과 다른 문의라서 따로 둔다 (legacy:제품군). 모델 카드로 합치지 않는다.
  const keyOf = (lines) => {
    const fam = lines.find((l) => l.startsWith('제품군: '))?.slice(5)
    const code = lines.find((l) => l.startsWith('모델: '))?.match(/\(([A-Za-z0-9-]+)\)\s*$/)?.[1]
    if (fam && lines.includes(`문의 유형: ${LEGACY_TOPIC}`)) return { fam, code: null, key: `legacy:${fam}` }
    return { fam, code, key: code && getProduct(code) ? code : fam ? `fam:${fam}` : null }
  }
  useEffect(() => {
    if (!context.length) return
    const { fam, code, key } = keyOf(context)
    if (!key) return
    if (dismissed && dismissed !== key) setDismissed(null)
    if (dismissed === key) return
    // 제품을 정하기 전에 나눈 대화는 처음 만든 제품 대화로 옮기고, 화면에서 고른 제품의 대화를 연다
    // 서버 세션도 같이 옮겨야 챗봇이 앞의 대화를 기억한다 (옮겨 갈 대화에 이미 세션이 있으면 그것을 쓴다)
    const ss = sessions.current
    const carried = ss[key] ?? ss._ ?? (code ? ss[`fam:${fam}`] : undefined)
    delete ss._
    if (code) delete ss[`fam:${fam}`]
    if (carried) ss[key] = carried
    setThreads((p) => {
      const old = code && p[`fam:${fam}`] // 제품군만 알던 대화는 모델이 정해지면 그 모델 대화로 잇는다
      const carry = [...(p._ ?? []), ...(old || [])]
      if (!carry.length) return p
      const { _, [`fam:${fam}`]: __, ...rest } = p
      return { ...rest, [key]: [...carry, ...(rest[key] ?? [])] }
    })
    activate(key)
    // 같은 제품이라도 문의 유형(고장·보증·설치 …)이 여러 개일 수 있다 — 카드에 태그로 쌓는다. 증상·에러코드는 유형이 아니라서 넣지 않는다.
    // 제품 고장은 증상을 고른 뒤에 태그로 붙인다(제품군·모델만 고른 단계에서 단종·호환 문의로 빠질 수 있다)
    const byView = { flow: context.some((l) => l.startsWith('증상: ')) && '제품 고장', guide: '설치 · 사용 방법', info: '제품 정보 · 자료' }[view]
    const topics = byView ? [byView] : context.filter((l) => /^(업무|문의 유형): /.test(l)).map((l) => l.slice(l.indexOf(': ') + 2)).filter(Boolean)
    setCards((prev) => {
      const before = [...prev.filter((c) => c.key === key), ...(code ? prev.filter((c) => c.key === `fam:${fam}`) : [])].flatMap((c) => c.topics ?? [])
      const merged = [...new Set([...before, ...topics])]
      return [{ key, lines: context, topics: merged }, ...prev.filter((c) => c.key !== key && !(code && c.key === `fam:${fam}`))]
    })
  }, [context]) // eslint-disable-line
  const removeCard = (key) => {
    const rest = cards.filter((c) => c.key !== key)
    setCards(rest); setDismissed(key)
    setThreads((p) => { const { [key]: _, ...r } = p; return r })
    if (activeRef.current === key) activate(rest[0]?.key ?? '_')
  }

  const appendTo = (key, role, content, extra) => setThreads((p) => ({ ...p, [key]: [...(p[key] ?? []), { id: crypto.randomUUID(), role, content, ...extra }] }))

  // 고객 말은 실제 챗봇(POST /api/chat)으로 보낸다. 답변의 이동 지시(navigation)는 제품 정보 화면으로, 문의서 전환(form)은 문의 남기기로 이어진다.
  // 제품마다 대화가 따로라서 서버 세션도 대화(thread)마다 따로 둔다.
  const langRef = useRef(lang); langRef.current = lang
  const TAB_OF = { info: 'spec', docs: 'docs', firmware: 'fw' }
  const send = useCallback((content, opts) => {
    const from = activeRef.current
    const uid = crypto.randomUUID(), pid = crypto.randomUUID()
    setThreads((p) => ({ ...p, [from]: [...(p[from] ?? []), { id: uid, role: 'user', content }] }))
    if (!opts?.reply) return
    // 펌웨어 업데이트·고장은 문의 유형이 없어서, 알아보면 챗봇 API를 거치지 않고 그 제품의 기술팀 연락처로 바로 잇는다
    const intent = firmwareIntent(content)
    if (intent) { const fw = firmwareReply(productOfKey(from), intent); appendTo(from, 'assistant', fw.content, { kind: 'fw', contact: fw.contact }); return }
    const mine = epoch.current
    const pendingMsg = { id: pid, role: 'assistant', content: '답변을 확인하고 있어요…', pending: true }
    setThreads((p) => ({ ...p, [from]: [...(p[from] ?? []), pendingMsg] }))
    const sid = (sessions.current[from] ??= crypto.randomUUID())
    api.chat({ session_id: sid, message: content, language: langRef.current, viewing_product: getProduct(from) ? from : null })
      .then((r) => ({ text: r.answer, nav: r.navigation, form: r.handoff && r.form ? r.form : null }))
      .catch((e) => ({ text: String(e?.message ?? '').startsWith('429') ? '요청이 많아서 잠깐 쉬고 있어요. 잠시 뒤에 다시 보내 주세요.' : '답변을 가져오지 못했어요. 입력한 내용은 그대로예요. 다시 시도해 주세요.', nav: null, form: null }))
      .then(({ text, nav: n, form }) => {
        if (mine !== epoch.current) return
        const code = n?.product_code && getProduct(n.product_code) ? n.product_code : null
        const to = code ?? from // 다른 제품을 물으면 그 제품의 대화로 옮겨 간다
        setThreads((p) => {
          const src = (p[from] ?? []).filter((m) => m.id !== pid && (to === from || m.id !== uid))
          const reply = { id: crypto.randomUUID(), role: 'assistant', content: text }
          if (to === from) return { ...p, [from]: [...src, reply] }
          return { ...p, [from]: src, [to]: [...(p[to] ?? []), { id: uid, role: 'user', content }, reply] }
        })
        if (to !== from && !sessions.current[to]) sessions.current[to] = sid // 옮겨 간 대화가 이 세션을 이어 쓴다
        if (code) activate(code)
        // 문의서를 쓰는 중에는 화면을 옮기지 않는다 (옮기면 작성 중인 문의서가 사라진다)
        const where = viewRef.current
        if (code && where !== 'inquire') {
          setNav({ family: getProduct(code).family, model: code, tab: TAB_OF[n.tab] ?? 'spec', attr: n.anchor, n: Date.now() }); setView('info')
        }
        // 서버가 펌웨어 문의서(FW_UPDATE)로 넘기려 해도 문의서를 열지 않고 기술팀 연락처를 안내한다 (펌웨어는 문의 유형이 없다)
        if (form?.category === 'FW_UPDATE') { const fw = firmwareReply(productOfKey(to), 'update'); appendTo(to, 'assistant', fw.content, { kind: 'fw', contact: fw.contact }) }
        else if (form && where !== 'inquire') openInquiry({ type: form.category ?? undefined, family: form.product_code ? getProduct(form.product_code)?.family : undefined, model: form.product_code ?? undefined, vals: form.fields, subject: form.subject, body: form.body })
      })
  }, []) // eslint-disable-line
  // 해결 화면의 [AI 상담에서 이어서 말하기]: 고객 말풍선이 아니라 챗봇이 먼저 "어느 제품으로 이어서 도울지"만 말하고, 말풍선 테두리가 잠깐 반응한다.
  // 증상·해 본 조치는 상단 "상담 중인 제품" 카드와 문의서 초안(chatDraft)에 이미 있어서 대화에 다시 적지 않는다.
  const handoff = (lines) => {
    const fam = lines.find((l) => l.startsWith('제품군: '))?.slice(5)
    const raw = lines.find((l) => l.startsWith('모델: '))?.slice(4) ?? ''
    const model = raw.replace(/\s*\([^()]*\)\s*$/, '')
    const who = [fam, model && !model.includes('잘 모르겠어요') ? model : ''].filter(Boolean).join(' · ')
    const { key } = keyOf(lines)
    appendTo(key ?? activeRef.current, 'assistant', `${who}로 이어서 도와드릴게요. 궁금한 점을 편하게 물어보세요.`, { kind: 'handoff', lines, flash: true })
    activate(key ?? activeRef.current)
    setChatFocus((n) => n + 1)
  }
  // 대화 내역과 대화에서 얻은 임시 정보를 지운다. 화면에서 고른 제품·모델과 이미 낸 문의는 그대로 둔다.
  const resetChat = () => { epoch.current += 1; delete sessions.current[activeRef.current]; setThreads((p) => ({ ...p, [activeRef.current]: [] })) }

  if (!onboarded) return <Onboarding onDone={(l) => { try { sessionStorage.setItem('ls-onboarded', '1'); sessionStorage.setItem('ls-lang', l) } catch { /* 무시 */ } setLang(l); setOnboarded(true) }} />

  return (
    <div className="page">
      <div className="main">
        <Header lang={lang} onLang={changeLang} onBack={() => { exit(); try { sessionStorage.removeItem('ls-onboarded') } catch { /* 무시 */ } setOnboarded(false) }} onHome={exit} onFaq={() => { exit(); setView('faq') }} onMine={() => { exit(); setOpenMine(null); setView('mine') }} onNew={() => { exit(); openInquiry({}) }} />
        {view === 'home' ? (
          <Hero onSelect={(t) => (t.id === 'stopped' ? setView('flow') : t.id === 'install' ? setView('guide') : t.id === 'info' ? setView('info') : t.id === 'warranty' ? setView('biz') : send(t.label))} />
        ) : view === 'guide' ? (
          <Guide onExit={exit} onContext={setContext} onInquire={openInquiry} />
        ) : view === 'mine' ? (
          <Inquiries key={openMine ?? 'list'} onNew={() => openInquiry({})} onSend={(t) => send(t)} onAgain={again} extra={submitted} initialOpen={openMine} />
        ) : view === 'inquire' ? (
          <Inquire key={JSON.stringify(draft)} draft={draft} lang={lang} onContext={setContext} onExit={exit}
            onSubmitted={(t) => setSubmitted((l) => [...l, t])} onOpenMine={(id) => { setOpenMine(id); setView('mine') }} />
        ) : view === 'replace' ? (
          <Replace key={replace?.family} family={replace?.family} onBack={() => setView(replace?.from && replace.from !== 'replace' ? replace.from : 'home')} onContext={setContext} onInquire={openInquiry} />
        ) : view === 'faq' ? (
          <FaqPage />
        ) : view === 'biz' ? (
          <Biz onExit={exit} onContext={setContext} onSend={send} onInquire={openInquiry} />
        ) : view === 'info' ? (
          <Info onExit={exit} onContext={setContext} onInquire={openInquiry} nav={nav} onNavDone={() => setNav(null)} />
        ) : (
          <Flow
            onExit={exit}
            onContext={setContext}
            onInquire={openInquiry}
            onHandoff={handoff}
          />
        )}
        <Footer />
      </div>
      <RightPanel messages={messages} onSend={(v) => send(v, { reply: true })} onReset={resetChat} focusKey={chatFocus} cards={cards} activeKey={activeKey} onActivate={(k) => { activate(k); setChatFocus((n) => n + 1) }} onRemoveCard={removeCard} onInquire={chatDraft} />
    </div>
  )
}
