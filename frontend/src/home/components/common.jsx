import { useEffect, useState } from 'react'
import { familyImage, getFamily, getProduct, products } from '../lib/catalog.js'
import MediaAttach from './MediaAttach.jsx'
import { hasLegacy, legacyDraft } from '../lib/legacy.js'
import FamilyCarousel from './FamilyCarousel.jsx'
import CuteIcon from './CuteIcon.jsx'

export const STEPS = ['제품군', '모델', '증상', '해결']
export const UNKNOWN = '__unknown'

export function Title({ emoji, icon, children, sub, tags }) {
  return (
    <div className="ftitle">
      <h2>{icon && <span className="emo emo-i" aria-hidden="true"><CuteIcon name={icon} size={28} /></span>}{children}</h2>
      {tags?.length > 0 && <ul className="ftags">{tags.map((g) => <li key={g.label} className={g.kind}>{g.label}</li>)}</ul>}
      {sub && <p>{sub}</p>}
    </div>
  )
}

export function Stepper({ step, onGo, labels = STEPS }) {
  return (
    <ol className="stepper" aria-label="진행 단계">
      {labels.map((l, i) => {
        const state = i < step ? 'done' : i === step ? 'now' : 'todo'
        return (
          <li key={l} className={state} aria-current={state === 'now' ? 'step' : undefined}>
            <button type="button" disabled={state !== 'done'} onClick={() => onGo(i)}
              aria-label={`${i + 1}단계 ${l}${state === 'done' ? ' (완료, 눌러서 돌아가기)' : state === 'now' ? ' (진행 중)' : ' (아직 안 함)'}`}>
              <span className="n">
                <span className="num">{i + 1}</span>
                <svg className="ck" viewBox="0 0 16 16" aria-hidden="true"><path d="M3.5 8.5l3 3 6-6.5" /></svg>
              </span>
              <span className="lb">{l}</span>
            </button>
            {i < labels.length - 1 && <span className="line" aria-hidden="true"><i className="fill" /></span>}
          </li>
        )
      })}
    </ol>
  )
}

export function FamilyStep({ s, pick, title = '어떤 제품에 문제가 생겼나요?', emoji }) {
  return (
    <>
      <Title>{title}</Title>
      <FamilyCarousel selected={s.family} onPick={pick} />
    </>
  )
}

// legacy = { onInquire }를 주면 변압기·차단기 제품군에서 제목 바로 아래, 모델 목록 위에 "단종 · 호환 · 대체 문의" 버튼을 보여 준다.
// 오래된 제품이라 모델 자체가 없거나 부품을 못 구하는 고객이 문의서로 바로 가는 길이다. 문의서 안에서는 주지 않는다.
// QR에서 읽은 값에 들어 있는 모델 코드 (없으면 null). 코드가 겹치면 긴 코드를 먼저 본다.
const CODES = Object.keys(products).sort((a, b) => b.length - a.length)
export const modelFromQr = (text) => CODES.find((c) => text.toUpperCase().includes(c.toUpperCase())) ?? null

// QR·사진으로 찾은 모델: 썸네일 · 모델명 · 고르기 버튼만 담은 작은 결과 카드
function FoundCard({ code, by, note, onPick }) {
  const p = getProduct(code)
  return (
    <div className="found" role="status">
      <img src={familyImage(p.family)} alt="" />
      <div className="found-t">
        <small>{by}{note && <i>{note}</i>}</small>
        <b>{p.name}</b>
        <span>{code}</span>
      </div>
      <button type="button" className="found-go" onClick={() => onPick(code)}>이 모델로 고르기</button>
    </div>
  )
}

// media/onMedia 를 주면 부모의 첨부 목록을 같이 쓴다 (제품 고장에서는 다음 단계 첨부로 이어진다). 안 주면 이 단계 안에서만 쓴다.
export function ModelStep({ s, pick, allowUnknown = true, legacy = null, media, onMedia }) {
  const fam = getFamily(s.family)
  const [own, setOwn] = useState([])
  const list = media ?? own
  const setList = onMedia ?? setOwn
  const found = [...new Set(list.filter((x) => x.kind === 'qr' && x.qr?.status === 'read').map((x) => modelFromQr(x.qr.text)).filter(Boolean))]
  // 시연용 사진 인식: 실제 인식 모델이 없어서, 올린 사진(이름·크기)으로 이 제품군 모델 하나를 고정해서 고른다.
  // 같은 사진은 늘 같은 모델이 나온다. 잠깐 "확인 중"을 보여 준 뒤 결과를 낸다.
  const photo = list.filter((x) => x.kind === 'photo').at(-1)
  const [seen, setSeen] = useState(null) // 결과를 낸 사진 id
  useEffect(() => {
    if (!photo || photo.id === seen) return
    const t = setTimeout(() => setSeen(photo.id), 1200)
    return () => clearTimeout(t)
  }, [photo?.id]) // eslint-disable-line
  const guess = photo && photo.id === seen ? fam.models[[...`${photo.file.name}${photo.file.size}`].reduce((h, ch) => (h * 31 + ch.charCodeAt(0)) >>> 0, 7) % fam.models.length] : null
  return (
    <>
      <Title emoji="🔎" sub={`${fam.name}에서 문제가 생긴 모델을 골라 주세요.`}>어떤 모델인가요?</Title>
      <div className="model-id">
        <MediaAttach value={list} onChange={setList} kinds={['qr', 'photo']} title="모델을 찾기 어려우면 QR이나 외관 사진을 올려 주세요"
          hints={{ qr: '제품에 붙은 QR 사진', photo: '제품 전체 · 명판 사진' }} />
        {photo && !guess && <p className="photo-check" role="status">사진에서 모델을 찾는 중이에요…</p>}
        {guess && !found.includes(guess) && (
          <FoundCard code={guess} by="사진으로 찾은 모델" note="시연용 결과예요" onPick={pick} />
        )}
        {found.map((c) => (getProduct(c).family === s.family
          ? <FoundCard key={c} code={c} by="QR에서 찾은 모델" onPick={pick} />
          : <p key={c} className="m-note">QR에서 찾은 모델 {getProduct(c).name} ({c})은 {getFamily(getProduct(c).family).name} 제품이에요. 제품군을 다시 골라 주세요.</p>))}
      </div>
      <div className="opt-list">
        {fam.models.map((c) => {
          const p = getProduct(c)
          return (
            <button type="button" key={c} className={`opt${s.model === c ? ' sel' : ''}`} onClick={() => pick(c)}>
              <b>{p.name}</b><small>{p.code}</small>
            </button>
          )
        })}
        {allowUnknown && (
          <button type="button" className={`opt ghost${s.model === UNKNOWN ? ' sel' : ''}`} onClick={() => pick(UNKNOWN)}>
            <b>모델을 잘 모르겠어요</b><small>{fam.name} 전체에서 증상으로 찾아볼게요</small>
          </button>
        )}
      </div>
      {legacy && hasLegacy(s.family) && (
        <button type="button" className="legacy-cta" onClick={() => legacy.onInquire?.(legacyDraft({ family: s.family, familyName: fam.name }))}>
          <span className="lc-txt"><b>단종 · 호환 · 대체 문의</b><small>오래돼서 부품을 구하기 어렵거나, 대체 모델이 필요해요</small></span>
          <svg className="lc-go" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M9 5l7 7-7 7" /></svg>
        </button>
      )}
    </>
  )
}


// 고른 순서대로 쌓이는 선택 경로 태그 (제품군 → 모델 → 목적 …). 새로 생긴 태그만 짧게 나타난다.
// onClick 이 있는 태그는 눌러서 그 단계로 돌아가 고칠 수 있다.
export function PathTags({ items }) {
  const list = items.filter((x) => x.label)
  if (!list.length) return null
  return (
    <ul className="ptags" aria-label="선택한 내용">
      {list.map((x) => (
        <li key={`${x.key}-${x.label}`} className="pt-li">
          {x.onClick
            ? <button type="button" className="pt is-btn" onClick={x.onClick} aria-label={`${x.key} ${x.label} 고치기`}><i>{x.key}</i>{x.label}</button>
            : <span className="pt"><i>{x.key}</i>{x.label}</span>}
        </li>
      ))}
    </ul>
  )
}
