import { useState } from 'react'
import { getFamily, getProduct } from '../lib/catalog.js'
import ProductTree from '../../pages/customer/ProductTree'
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

// 제품군 고르기: 왼쪽 제품 목록(CSA-39 고객 화면의 ProductTree · 접는 막대 그대로) + 회전 캐러셀.
// 목록은 처음엔 접혀 있고(얇은 막대) 눌러서 펼친다. 제품군 이름을 누르면 캐러셀이 그 제품군으로 돌고,
// 모델을 누르면 그 모델을 바로 고른다 (pickModel(제품군, 모델)).
export function FamilyStep({ s, pick, pickModel, title = '어떤 제품에 문제가 생겼나요?', emoji }) {
  const [treeOpen, setTreeOpen] = useState(false)
  const [focus, setFocus] = useState(null)
  const focusFamily = (family) => setFocus((f) => ({ family, n: (f?.n ?? 0) + 1 }))
  const selectModel = (code) => { const p = getProduct(code); if (p) pickModel(p.family, code) }
  return (
    <>
      <Title>{title}</Title>
      <div className="fpick">
        <div className={`cs-side${treeOpen ? ' is-tree' : ''}`}>
          <button type="button" className="cs-side-btn" aria-controls="cs-tree" aria-expanded={treeOpen} onClick={() => setTreeOpen((o) => !o)}>
            <span aria-hidden="true">{treeOpen ? '«' : '☰'}</span>
            <span>{treeOpen ? '목록 접기' : '제품 목록'}</span>
          </button>
          {treeOpen && <ProductTree id="cs-tree" selected={s.model ?? null} onSelect={selectModel} onFamily={focusFamily} />}
        </div>
        <div className="fpick-main">
          <FamilyCarousel selected={s.family} onPick={pick} focus={focus} />
        </div>
      </div>
    </>
  )
}

export function ModelStep({ s, pick, allowUnknown = true }) {
  const fam = getFamily(s.family)
  return (
    <>
      <Title emoji="🔎" sub={`${fam.name}에서 문제가 생긴 모델을 골라 주세요.`}>어떤 모델인가요?</Title>
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
