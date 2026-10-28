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
import Onboarding from './components/Onboarding.jsx'
import { initialLang, loadChoice, saveChoice } from './lib/onboarding.js'
import { getProduct } from './lib/catalog.js'

export default function App() {
  const [onboarded, setOnboarded] = useState(() => { try { return sessionStorage.getItem('ls-onboarded') === '1' } catch { return false } })
  // 화면 언어: 온보딩에서 정한 값(이번 세션) → 직접 고른 값 → 브라우저·영어. 헤더에서 바꾸면 선택으로 저장한다.
  const [lang, setLang] = useState(() => {
    let s = null
    try { s = sessionStorage.getItem('ls-lang') } catch { /* 무시 */ }
    return s || loadChoice() || initialLang({ choice: null, country: null }).lang
  })
  const changeLang = (l) => { setLang(l); saveChoice(l); try { sessionStorage.setItem('ls-lang', l) } catch { /* 무시 */ } }
  // 제품 하나당 대화 하나: 카드 키(모델 코드 또는 fam:제품군)별 대화. 제품을 아직 모르면 '_' 대화.
  const [threads, setThreads] = useState({})
  const [activeKey, setActiveKey] = useState('_')
  const activeRef = useRef('_')
  const activate = (key) => { activeRef.current = key; setActiveKey(key) }
  const messages = threads[activeKey] ?? []
  const [view, setView] = useState('home')
  const [context, setContext] = useState([])
  const [chatFocus, setChatFocus] = useState(0) // 올라갈 때마다 AI 상담 입력창에 커서를 둔다
  const [cards, setCards] = useState([]) // 상담 중인 제품 카드들 (본 제품이 쌓인다. 최근 것이 위)
  const [dismissed, setDismissed] = useState(null) // 지운 카드의 키 — 같은 제품을 계속 보는 동안 다시 만들지 않는다
  const epoch = useRef(0) // 대화 초기화 때마다 올라간다 — 초기화 전에 요청한 답변은 버린다
  const [draft, setDraft] = useState(null)
  const [submitted, setSubmitted] = useState([])
  const [openMine, setOpenMine] = useState(null)
  const exit = () => { setView('home'); setContext([]) }

  const openInquiry = (d = {}) => { setDraft(d); setView('inquire') }
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
  const keyOf = (lines) => {
    const fam = lines.find((l) => l.startsWith('제품군: '))?.slice(5)
    const code = lines.find((l) => l.startsWith('모델: '))?.match(/\(([A-Za-z0-9-]+)\)\s*$/)?.[1]
    return { fam, code, key: code && getProduct(code) ? code : fam ? `fam:${fam}` : null }
  }
  useEffect(() => {
    if (!context.length) return
    const { fam, code, key } = keyOf(context)
    if (!key) return
    if (dismissed && dismissed !== key) setDismissed(null)
    if (dismissed === key) return
    // 제품을 정하기 전에 나눈 대화는 처음 만든 제품 대화로 옮기고, 화면에서 고른 제품의 대화를 연다
    setThreads((p) => {
      const old = code && p[`fam:${fam}`] // 제품군만 알던 대화는 모델이 정해지면 그 모델 대화로 잇는다
      const carry = [...(p._ ?? []), ...(old || [])]
      if (!carry.length) return p
      const { _, [`fam:${fam}`]: __, ...rest } = p
      return { ...rest, [key]: [...carry, ...(rest[key] ?? [])] }
    })
    activate(key)
    // 같은 제품이라도 문의 유형(고장·보증·설치 …)이 여러 개일 수 있다 — 카드에 태그로 쌓는다. 증상·에러코드는 유형이 아니라서 넣지 않는다.
    const byView = { flow: '제품 고장', guide: '설치 · 사용 방법', info: '제품 정보 · 자료' }[view]
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

  // 챗봇 API(/chat)는 아직 없다. 지금은 고객 말을 지금 열린 제품 대화에 쌓아 두기만 하고, 답변이나 화면 이동은 하지 않는다.
  const send = useCallback((content) => { appendTo(activeRef.current, 'user', content) }, []) // eslint-disable-line
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
  const resetChat = () => { epoch.current += 1; setThreads((p) => ({ ...p, [activeRef.current]: [] })) }

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
          <Inquire key={JSON.stringify(draft)} draft={draft} onContext={setContext} onExit={exit}
            onSubmitted={(t) => setSubmitted((l) => [...l, t])} onOpenMine={(id) => { setOpenMine(id); setView('mine') }} />
        ) : view === 'faq' ? (
          <FaqPage />
        ) : view === 'biz' ? (
          <Biz onExit={exit} onContext={setContext} onSend={send} onInquire={openInquiry} />
        ) : view === 'info' ? (
          <Info onExit={exit} onContext={setContext} onInquire={openInquiry} />
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
      <RightPanel messages={messages} onSend={send} onReset={resetChat} focusKey={chatFocus} cards={cards} activeKey={activeKey} onActivate={(k) => { activate(k); setChatFocus((n) => n + 1) }} onRemoveCard={removeCard} onInquire={chatDraft} />
    </div>
  )
}
