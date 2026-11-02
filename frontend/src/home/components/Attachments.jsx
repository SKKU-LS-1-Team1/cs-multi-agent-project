// 첨부 파일 목록: 사진은 썸네일로 보여 주고 누르면 크게 본다. 그 밖의 파일은 열기 링크.
// items: [{ name, size?, type?, url? }] — url 이 없으면 파일을 받을 수 없어 이름만 보인다.
import { useEffect, useState } from 'react'
import { humanSize } from '../lib/inquiryForm.js'

// 서버가 화면 안에서 열어 주는 형식만 (services/attachments.py INLINE_TYPES). SVG 등은 파일로 받는다
const isImage = (x) => x.url && (x.type ? /^image\/(png|jpeg|gif|webp|bmp)$/.test(x.type) : /\.(png|jpe?g|gif|webp|bmp)$/i.test(x.name))

export default function Attachments({ items }) {
  const [view, setView] = useState(null) // 크게 보는 사진의 순번
  const images = items.filter(isImage)
  const shown = view === null ? null : images[view]

  useEffect(() => {
    if (view === null) return
    const key = (e) => {
      if (e.key === 'Escape') setView(null)
      if (e.key === 'ArrowRight') setView((v) => (v + 1) % images.length)
      if (e.key === 'ArrowLeft') setView((v) => (v - 1 + images.length) % images.length)
    }
    window.addEventListener('keydown', key)
    return () => window.removeEventListener('keydown', key)
  }, [view, images.length])

  return (
    <>
      <ul className="att-grid">
        {items.map((x, i) => (
          <li key={`${x.name}-${i}`}>
            {isImage(x) ? (
              <button type="button" className="att-thumb" onClick={() => setView(images.indexOf(x))} aria-label={`${x.name} 크게 보기`}>
                <img src={x.url} alt="" loading="lazy" />
              </button>
            ) : (
              <a className={`att-thumb att-file${x.url ? '' : ' off'}`} href={x.url || undefined} target="_blank" rel="noreferrer" aria-label={x.url ? `${x.name} 열기` : undefined}>
                <span aria-hidden="true">{(x.name.split('.').pop() || 'FILE').slice(0, 4).toUpperCase()}</span>
              </a>
            )}
            <b title={x.name}>{x.name}</b>
            <small>{x.url ? (x.size ? humanSize(x.size) : '') : '파일 없음 · 이름만 기록'}</small>
          </li>
        ))}
      </ul>
      {shown && (
        <div className="att-view" role="dialog" aria-label={shown.name} onClick={() => setView(null)}>
          <figure onClick={(e) => e.stopPropagation()}>
            <img src={shown.url} alt={shown.name} />
            <figcaption>
              <span>{shown.name}{images.length > 1 && <em> · {view + 1}/{images.length}</em>}</span>
              <span>
                {images.length > 1 && <>
                  <button type="button" onClick={() => setView((view - 1 + images.length) % images.length)} aria-label="이전 사진">‹</button>
                  <button type="button" onClick={() => setView((view + 1) % images.length)} aria-label="다음 사진">›</button>
                </>}
                <a href={shown.url} download={shown.name}>저장</a>
                <button type="button" onClick={() => setView(null)} aria-label="닫기" autoFocus>✕</button>
              </span>
            </figcaption>
          </figure>
        </div>
      )}
    </>
  )
}
