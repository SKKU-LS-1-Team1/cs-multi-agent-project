// 제품 캐러셀 옆 "제품 목록" 탭 (예전 고객 화면 CSA-39 의 왼쪽 목록을 새 홈에 옮김).
// 처음엔 얇은 탭으로 접혀 있고 누르면 대분류 → 제품군 → 모델 목록이 펼쳐진다.
// 제품군이나 모델을 누르면 캐러셀이 그 제품군으로 돈다 (고르는 것은 캐러셀의 선택 버튼 그대로).
import { useEffect, useRef, useState } from 'react'
import { divisions, familyImage, getProduct } from '../lib/catalog.js'

export default function ProductList({ current, onFamily }) {
  const [open, setOpen] = useState(false)
  const box = useRef(null)
  // 캐러셀이 돌면 목록에서도 그 제품군이 보이게 (목록이 길어 아래쪽 제품군은 가려진다)
  useEffect(() => {
    box.current?.querySelector('.plist-fam.is-cur')?.scrollIntoView({ block: 'nearest' })
  }, [current, open])
  if (!open) {
    return (
      <button type="button" className="plist-tab" aria-controls="plist" aria-expanded="false" onClick={() => setOpen(true)}>
        <span aria-hidden="true">☰</span><span className="plist-tab-label">제품 목록</span>
      </button>
    )
  }
  return (
    <aside id="plist" ref={box} className="plist" aria-label="제품 목록">
      <div className="plist-head">
        <b>제품 목록</b>
        <button type="button" className="plist-close" aria-controls="plist" aria-expanded="true" onClick={() => setOpen(false)}>« 접기</button>
      </div>
      {divisions.map((d) => (
        <section key={d.id} className="plist-div">
          <h4>{d.label}</h4>
          {d.families.map((f) => (
            <details key={f.id} className={`plist-fam${f.id === current ? ' is-cur' : ''}`} open={f.id === current}>
              <summary onClick={() => onFamily(f.id)}>
                <img src={familyImage(f.id)} alt="" width="28" height="28" />
                <span>{f.name}</span>
                <em>{f.models.length}</em>
              </summary>
              {f.models.map((code) => (
                <button type="button" key={code} className="plist-item" onClick={() => onFamily(f.id)}>
                  {getProduct(code)?.name || code}
                </button>
              ))}
            </details>
          ))}
        </section>
      ))}
    </aside>
  )
}
