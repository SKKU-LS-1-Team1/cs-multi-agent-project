import { useId, useRef, useState } from 'react'
import CuteIcon from './CuteIcon.jsx'
import { humanSize } from '../lib/inquiryForm.js'
import { KINDS, MAX_PER_KIND, kindOf, readQr, rejectReason } from '../lib/media.js'

// 제품 고장 → 증상 단계 맨 위의 첨부 영역: 사진 · 영상 · 소리 · QR.
// 선택 사항이라 올리지 않아도 다음으로 갈 수 있다. 목업이라 서버로 보내지 않고 이 브라우저 안에서만 미리 본다.
// value = 올린 목록, onChange = 부모 state 설정 함수(함수형 업데이트를 받는다). 목록은 부모가 쥐고 있어 단계를 오가도 남는다.
// 미리보기 주소(object URL)는 지울 때 여기서 풀고, 화면을 완전히 나갈 때는 부모가 푼다.
const QR_NOTE = {
  checking: 'QR을 읽는 중이에요…',
  none: 'QR을 찾지 못했어요. 더 가까이서 다시 찍어 주세요.',
  unsupported: 'QR 사진으로 올렸어요. 이 브라우저는 자동으로 읽지 못해요.',
}

// kinds = 보여 줄 첨부 종류(기본은 전부), title = 제목, hints = 종류별 설명 바꾸기 { qr: '...' }
export default function MediaAttach({ value, onChange, kinds = KINDS.map((k) => k.key), title = '고장 모습을 보여 주세요', hints = {} }) {
  const shown = KINDS.filter((k) => kinds.includes(k.key))
  const MB = { photo: '사진 20MB', video: '영상 200MB', sound: '소리 50MB', qr: 'QR 10MB' }
  const id = useId()
  const refs = useRef({})
  const [notes, setNotes] = useState([])

  const add = (kindKey, files) => {
    const current = value.filter((x) => x.kind === kindKey)
    const accepted = []
    const problems = []
    for (const file of files) {
      const why = rejectReason(kindKey, file, [...current, ...accepted])
      if (why) problems.push(why)
      else accepted.push({ id: `${kindKey}-${file.name}-${file.size}-${Math.random().toString(36).slice(2)}`, kind: kindKey, file, url: URL.createObjectURL(file), qr: kindKey === 'qr' ? { status: 'checking' } : null })
    }
    // 같은 종류의 개수 제한 안내는 한 번만 보여 준다
    setNotes([...new Set(problems)])
    if (!accepted.length) return
    onChange((cur) => [...cur, ...accepted])
    if (kindKey === 'qr') {
      accepted.forEach((item) => readQr(item.file).then((qr) => onChange((cur) => cur.map((x) => (x.id === item.id ? { ...x, qr } : x)))))
    }
  }

  const remove = (item) => {
    URL.revokeObjectURL(item.url)
    onChange((cur) => cur.filter((x) => x.id !== item.id))
    setNotes([])
  }

  return (
    <section className="media" aria-labelledby={id}>
      <div className="media-h">
        <b id={id}>{title}</b>
        <em className="m-opt">선택</em>
      </div>
      <div className={`media-tiles n${shown.length}`} style={{ '--n': shown.length }}>
        {shown.map((k) => {
          const n = value.filter((x) => x.kind === k.key).length
          return (
            <button type="button" key={k.key} className="mtile" onClick={() => refs.current[k.key]?.click()}
              aria-label={`${k.label} 올리기${n ? `, ${n}개 올림` : ''}`}>
              <CuteIcon name={k.icon} size={34} />
              <b>{k.label}</b>
              <small>{hints[k.key] ?? k.hint}</small>
              {n > 0 && <i className="mcount" aria-hidden="true">{n}</i>}
            </button>
          )
        })}
      </div>
      {/* 파일 선택창은 버튼 밖에 둔다(버튼 안에 입력 요소를 넣을 수 없다). 버튼이 아래 입력을 대신 눌러 준다. */}
      {shown.map((k) => (
        <input key={k.key} ref={(el) => { refs.current[k.key] = el }} type="file" hidden multiple accept={k.accept} tabIndex={-1}
          aria-label={`${k.label} 파일 선택`} onChange={(e) => { add(k.key, [...e.target.files]); e.target.value = '' }} />
      ))}
      <p className="m-limit">종류마다 최대 {MAX_PER_KIND}개 · {shown.map((k) => MB[k.key]).join(' · ')}까지</p>
      <p className="m-note" role="status" aria-live="polite">{notes.join(' · ')}</p>
      {value.some((x) => kinds.includes(x.kind)) && (
        <ul className="mlist" aria-label="올린 파일">
          {value.filter((x) => kinds.includes(x.kind)).map((x) => {
            const k = kindOf(x.kind)
            return (
              <li key={x.id} className={`m-${x.kind}`}>
                <span className="mthumb">
                  {(x.kind === 'photo' || x.kind === 'qr') && <img src={x.url} alt={`${x.file.name} 미리보기`} />}
                  {x.kind === 'video' && <video src={`${x.url}#t=0.1`} preload="metadata" muted aria-label={`${x.file.name} 미리보기`} />}
                  {x.kind === 'sound' && <CuteIcon name="sound" size={30} />}
                </span>
                <span className="mbody">
                  <b title={x.file.name}>{x.file.name}</b>
                  <small>{k.label} · {humanSize(x.file.size)}</small>
                  {x.kind === 'sound' && <audio src={x.url} controls preload="metadata" aria-label={`${x.file.name} 재생`} />}
                  {x.kind === 'video' && <details className="m-play"><summary>영상 재생</summary><video src={x.url} controls preload="metadata" /></details>}
                  {x.kind === 'qr' && x.qr && (
                    x.qr.status === 'read'
                      // QR 내용은 글자로만 보여 준다. 링크로 열지 않는다.
                      ? <small className="m-qr ok">읽은 값: <code>{x.qr.text}</code></small>
                      : <small className={`m-qr${x.qr.status === 'none' ? ' warn' : ''}`}>{QR_NOTE[x.qr.status]}</small>
                  )}
                </span>
                <button type="button" className="mdel" aria-label={`${x.file.name} 삭제`} onClick={() => remove(x)}>삭제</button>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
