import { useEffect, useId, useMemo, useState } from 'react'
import { getFamily, getProduct } from '../lib/catalog.js'
import { LEGACY_TOPIC, legacyDraft } from '../lib/legacy.js'
import { CRITERIA, LIFECYCLE, STATUS, compare, fromProduct, loadInfo, quoteDraft } from '../lib/replace.js'
import { Title } from './common.jsx'

// 단종 · 호환 · 대체 문의의 첫 화면: 쓰던 제품의 정격을 알려 주면 현재 판매 중인 모델과 비교해 대체 모델을 추천한다.
// 모델을 고르면 견적 문의서가 비교 결과와 함께 채워진 채로 열린다(onInquire). 맞는 모델이 없을 때만 단종 · 호환 문의서로 바로 간다.
// data·initial은 미리보기·검증용(주지 않으면 스펙을 불러오고 빈 입력으로 시작한다).
const MARK = { same: '✓', ok: '✓', near: '!', low: '✕', unknown: '–' }

function Field({ c, value, bad, onChange }) {
  const id = useId()
  return (
    <div className="fld">
      <label htmlFor={id}><span>{c.label}{c.unit && <em className="rep-unit">{c.unit}</em>}</span></label>
      {c.kind === 'select' ? (
        <select id={id} className="qin" value={value} onChange={(e) => onChange(e.target.value)}>
          <option value="">잘 모르겠어요</option>
          {c.options.map((o) => <option key={o} value={o}>{o}</option>)}
        </select>
      ) : (
        <input id={id} className="qin" type={c.kind === 'number' ? 'number' : 'text'} inputMode={c.kind === 'number' ? 'decimal' : undefined}
          min={c.kind === 'number' ? 0 : undefined} step={c.kind === 'number' ? 'any' : undefined} maxLength={c.kind === 'text' ? 20 : undefined}
          value={value} placeholder={c.placeholder} aria-invalid={bad || undefined} onChange={(e) => onChange(e.target.value)} />
      )}
      {bad && <small className="rep-bad" role="alert">{c.kind === 'number' ? '0보다 큰 숫자로 적어 주세요' : '20자 안으로 적어 주세요'}</small>}
    </div>
  )
}

// 카드를 누르면 고른 카드가 되고, 그 카드 아래에만 견적 문의 버튼이 생긴다. 조건이 맞지 않는 모델도 견적 문의할 수 있다.
function Candidate({ row, top, selected, onSelect, onPick }) {
  const m = row.master
  return (
    <article className={`rep-card${top ? ' top' : ''}${row.fit ? '' : ' off'}${selected ? ' sel' : ''}`} aria-label={`${row.name} 비교`}
      tabIndex={0} aria-selected={selected} onClick={() => onSelect(row.code)}
      onKeyDown={(e) => { if (e.target === e.currentTarget && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); onSelect(row.code) } }}>
      <div className="rep-head">
        <div className="rep-name">
          <b>{row.name}</b>
          <small>{row.code}</small>
        </div>
        <div className="rep-tags">
          {top && <span className="rep-badge">가장 비슷해요</span>}
          <span className="rep-chip">{LIFECYCLE[m.lifecycle_status] ?? m.lifecycle_status}</span>
        </div>
      </div>
      <div className="rep-tablewrap">
        <table className="rep-table">
          <thead><tr><th scope="col">항목</th><th scope="col">쓰던 제품</th><th scope="col">이 모델</th><th scope="col">판정</th></tr></thead>
          <tbody>
            {row.checks.map((x) => (
              <tr key={x.key}>
                <th scope="row">{x.label}</th>
                <td>{x.mine}</td>
                <td>{x.theirs}{x.note && <small className="rep-note">{x.note}</small>}</td>
                <td><span className={`st ${x.status}`}><i aria-hidden="true">{MARK[x.status]}</i>{STATUS[x.status]}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="rep-meta">표준 납기 {m.std_lead_time_weeks}주 · 최소 주문 {m.moq}개 · {String(m.standards).replace(/;/g, ' · ')}</p>
      {selected && (
        <div className={`rep-act${row.fit ? '' : ' has-warn'}`}>
          {!row.fit && (
            <p className="rep-warn"><i aria-hidden="true">!</i>
              <span><b>맞지 않는 항목 {row.counts.low}개</b>비교 결과와 함께 보내면 담당 기술지원이 대체 가능한지 확인해요.</span></p>
          )}
          <button type="button" className="pbtn" onClick={(e) => { e.stopPropagation(); onPick(row) }}>이 모델로 견적 문의하기</button>
        </div>
      )}
    </article>
  )
}

export default function Replace({ family, onBack, onContext, onInquire, data = null, initial = null }) {
  const fam = getFamily(family)
  const [info, setInfo] = useState(data)
  const [values, setValues] = useState(initial?.values ?? {})
  const [ref, setRef] = useState(initial?.ref ?? '')
  const [chosen, setChosen] = useState(null) // 견적 문의 버튼을 보여 줄 카드 (고르기 전에는 가장 비슷한 모델)
  const [old, setOld] = useState(initial?.ref ? getProduct(initial.ref)?.name ?? '' : '') // 쓰던 모델 (직접 적거나 카탈로그에서 고른다)
  useEffect(() => { if (!data) loadInfo().then(setInfo) }, [data])
  // 챗봇 상단 카드: 모델은 아직 모르고, 단종·호환 문의 중이라고 알린다
  useEffect(() => { onContext?.([`제품군: ${fam.name}`, '모델: 모델을 잘 모르겠어요', `문의 유형: ${LEGACY_TOPIC}`]) }, [fam.name, onContext])

  const res = useMemo(() => compare(family, values, info), [family, values, info])
  const sel = res.rows.some((r) => r.code === chosen) ? chosen : res.fits[0]?.code ?? null
  const set = (key, v) => { setValues((c) => ({ ...c, [key]: v })); setRef('') }
  const fill = (code) => { setRef(code); setValues(code ? fromProduct(family, code, info) : {}) }
  // 적은 값이 카탈로그 모델 이름이나 코드와 같으면 그 모델 정격으로 채운다. 아니면 직접 적은 모델명으로 두고 정격은 직접 입력한다.
  const catalog = fam.models.filter((c) => info?.[c])
  const typeOld = (v) => {
    setOld(v)
    const t = v.trim().toLowerCase()
    const hit = catalog.find((c) => c.toLowerCase() === t || getProduct(c).name.toLowerCase() === t)
    if (hit) fill(hit)
    else if (ref) setRef('')
  }
  const oldLine = old.trim() ? [`기존 제품 모델: ${old.trim()}`] : []
  const pick = (row) => { const d = quoteDraft({ family, row, entered: res.entered }); onInquire?.(oldLine.length ? { ...d, body: d.body.replace('\n', `\n${oldLine[0]}\n`) } : d) }
  const direct = () => onInquire?.({ ...legacyDraft({ family, familyName: fam.name }), direct: true, ...(old.trim() ? { vals: { product_model: old.trim() } } : {}) })

  return (
    <div className="flow replace">
      <div className="fhead"><button type="button" className="backbtn" onClick={onBack}>← 이전</button></div>
      <Title>대체 모델 찾기</Title>

      <section className="rep-sec" aria-label="쓰던 제품 정격">
        <h3>쓰던 {fam.name}의 정격</h3>
        <div className="rep-form">
          <div className="fld rep-fill">
            <label htmlFor="rep-ref"><span>쓰던 모델</span><small>명판에 적힌 모델명을 적어 주세요. 목록에 있는 모델을 고르면 정격이 자동으로 채워져요.</small></label>
            <input id="rep-ref" className="qin" list="rep-ref-list" value={old} maxLength={60} autoComplete="off"
              placeholder="예: ABS-103b, 또는 목록에서 고르기" onChange={(e) => typeOld(e.target.value)} />
            <datalist id="rep-ref-list">
              {catalog.map((c) => <option key={c} value={getProduct(c).name}>{c}</option>)}
            </datalist>
            {ref && <small className="rep-filled">카탈로그 모델 {getProduct(ref).name} ({ref})의 정격으로 채웠어요. 고쳐도 돼요.</small>}
          </div>
          <div className="rep-grid">
            {(CRITERIA[family] ?? []).map((c) => <Field key={c.key} c={c} value={values[c.key] ?? ''} bad={res.invalid.includes(c.key)} onChange={(v) => set(c.key, v)} />)}
          </div>
        </div>
      </section>

      <section className="rep-sec" aria-label="추천 모델" aria-live="polite">
        <h3>추천 모델{res.rows.length > 0 && <em className="rep-count">{res.fits.length}개</em>}</h3>
        {!info && <p className="rep-empty">사양을 불러오는 중이에요…</p>}
        {info && res.entered.length === 0 && <p className="rep-empty">정격을 하나 이상 입력하면 비교해 드려요.</p>}
        {info && res.entered.length > 0 && res.fits.length === 0 && (
          <div className="rep-none" role="status">
            <b>조건에 맞는 모델이 없어요</b>
            <p>담당 기술지원이 대체 방법을 확인해 드려요.</p>
            <button type="button" className="pbtn" onClick={direct}>단종 · 호환 문의하기</button>
          </div>
        )}
        {res.fits.map((row, i) => <Candidate key={row.code} row={row} top={i === 0} selected={sel === row.code} onSelect={setChosen} onPick={pick} />)}
        {res.misfits.length > 0 && (
          <details className="rep-more">
            <summary>조건이 맞지 않는 모델 {res.misfits.length}개</summary>
            {res.misfits.map((row) => <Candidate key={row.code} row={row} top={false} selected={sel === row.code} onSelect={setChosen} onPick={pick} />)}
          </details>
        )}
      </section>

    </div>
  )
}
