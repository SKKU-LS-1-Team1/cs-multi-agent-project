import { useEffect, useRef, useState } from 'react'
import { families, familyImage } from '../lib/catalog.js'

const N = families.length
const STEP = (2 * Math.PI) / N // 한 칸 = 수평 원형 궤도의 한 자리
const RX = 430 // 궤도 가로 반지름
const RZ = 340 // 궤도 앞뒤 깊이
const TILT = 0.55 // 중심을 향해 기울이는 정도 (궤도 각도 대비)
const MAX_TILT = 38 // 이 이상 돌리면 납작해지므로 각도 상한(deg)
const DRAG_PX = 120 // 이만큼 끌면 한 칸
const K = 80 // 정렬 스프링 세기 (임계 감쇠라 튕기지 않는다)
const mod = (x) => ((x % N) + N) % N
const wrap = (x) => ((((x + N / 2) % N) + N) % N) - N / 2
const clamp = (v, a, b) => Math.min(b, Math.max(a, v))
const reduced = () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

export default function FamilyCarousel({ selected, onPick }) {
  const start = Math.max(0, families.findIndex((f) => f.id === selected))
  // pos: 연속 위치(소수). 정수에 있으면 그 제품이 정중앙. 한 바퀴 넘어도 끊기지 않게 모듈러 없이 누적한다.
  const [pos, setPos] = useState(start)
  const [dragging, setDragging] = useState(false)
  const s = useRef({ pos: start, vel: 0, target: start, raf: 0, last: 0, drag: null })
  const moved = useRef(false)

  const step = (t) => {
    const m = s.current
    const dt = Math.min(0.032, (t - m.last) / 1000 || 0.016)
    m.last = t
    // 임계 감쇠 스프링: 목표로 부드럽게 감속하며 들어온다. (놓았을 때의 속도가 관성이 된다)
    const c = 2 * Math.sqrt(K)
    m.vel += (K * (m.target - m.pos) - c * m.vel) * dt
    m.pos += m.vel * dt
    if (Math.abs(m.target - m.pos) < 0.0006 && Math.abs(m.vel) < 0.002) {
      m.pos = m.target; m.vel = 0; m.raf = 0
    } else m.raf = requestAnimationFrame(step)
    setPos(m.pos)
  }
  const run = () => { if (!s.current.raf) { s.current.last = performance.now(); s.current.raf = requestAnimationFrame(step) } }
  useEffect(() => () => cancelAnimationFrame(s.current.raf), [])

  const goTo = (target) => {
    const m = s.current
    m.target = target
    if (reduced()) { m.pos = target; m.vel = 0; setPos(target) } else run()
  }
  const go = (n) => goTo(Math.round(s.current.target) + n)

  const onDown = (e) => {
    const m = s.current
    cancelAnimationFrame(m.raf); m.raf = 0; m.vel = 0
    m.drag = { x: e.clientX, p: m.pos, id: e.pointerId, lx: e.clientX, lt: performance.now(), v: 0 }
    moved.current = false
  }
  const onMove = (e) => {
    const m = s.current
    if (!m.drag) return
    const dx = e.clientX - m.drag.x
    if (!moved.current && Math.abs(dx) > 6) {
      moved.current = true
      setDragging(true)
      e.currentTarget.setPointerCapture(m.drag.id)
    }
    if (!moved.current) return
    const now = performance.now()
    const v = (-(e.clientX - m.drag.lx) / DRAG_PX) / Math.max(0.001, (now - m.drag.lt) / 1000)
    m.drag.v = m.drag.v * 0.6 + v * 0.4
    m.drag.lx = e.clientX; m.drag.lt = now
    m.pos = m.drag.p - dx / DRAG_PX
    setPos(m.pos)
  }
  const onUp = () => {
    const m = s.current
    if (!m.drag) return
    const v = m.drag.v
    m.drag = null
    setDragging(false)
    if (!moved.current) return
    // 놓은 속도만큼 더 미끄러진 뒤 가장 가까운 제품에 정렬
    const t = Math.round(m.pos + clamp(v, -8, 8) * 0.16)
    m.vel = clamp(v, -8, 8)
    goTo(t)
  }
  const onKey = (e) => {
    if (e.key === 'ArrowLeft') { e.preventDefault(); go(-1) }
    if (e.key === 'ArrowRight') { e.preventDefault(); go(1) }
  }

  const index = mod(Math.round(pos))
  const cur = families[index]

  return (
    <div className="car" role="group" aria-roledescription="carousel" aria-label="제품군" onKeyDown={onKey}>
      <div className="car-jump" role="group" aria-label="제품군 바로 보기">
        {families.map((f, i) => (
          <button type="button" key={f.id} className={i === index ? 'sel' : ''} aria-pressed={i === index}
            onClick={() => goTo(Math.round(s.current.target) + wrap(i - Math.round(s.current.target)))}>
            {f.name}
          </button>
        ))}
      </div>

      <div className="car-view">
        <div className="car-fade">
          <div className={`car-stage${dragging ? ' dragging' : ''}`}
            onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onPointerCancel={onUp}>
            {families.map((f, i) => {
              const d = wrap(i - pos) // 중앙에서 떨어진 칸 수 (부호: 오른쪽 +)
              const a = Math.abs(d)
              const th = d * STEP
              const x = Math.sin(th) * RX
              const z = (Math.cos(th) - 1) * RZ
              const tilt = -clamp(th * TILT * (180 / Math.PI), -MAX_TILT, MAX_TILT) // 바깥쪽 제품이 중심을 바라본다
              const scale = 1 - 0.07 * Math.min(a, 3)
              const opacity = clamp(1 - 0.3 * a - 0.04 * a * a, 0, 1) // 옆 제품은 알아볼 만큼, 바깥은 점점 희미하게
              const blur = Math.min(a, 3.5) * 1.3
              const center = Math.round(d) === 0
              return (
                <button type="button" key={f.id} tabIndex={center ? 0 : -1}
                  className={`car-item${center ? ' center' : ''}`}
                  aria-label={center ? `${f.name} (현재 선택 중)` : `${f.name} 보기`} aria-current={center}
                  style={{
                    transform: `translate3d(${x.toFixed(1)}px,0,${z.toFixed(1)}px) rotateY(${tilt.toFixed(2)}deg) scale(${scale.toFixed(3)})`,
                    opacity: opacity.toFixed(3), filter: blur > 0.05 ? `blur(${blur.toFixed(2)}px)` : 'none',
                    zIndex: Math.round(100 - a * 10), pointerEvents: a > 3 ? 'none' : 'auto',
                  }}
                  onClick={() => { if (!moved.current && !center) goTo(Math.round(s.current.target + d)) }}>
                  <img src={familyImage(f.id)} alt="" draggable="false" />
                </button>
              )
            })}
          </div>
        </div>
        <button type="button" className="car-arrow l" aria-label="이전 제품군" onClick={() => go(-1)}>‹</button>
        <button type="button" className="car-arrow r" aria-label="다음 제품군" onClick={() => go(1)}>›</button>
      </div>

      <div className="car-info" aria-live="polite">
        <h3>{cur.name}</h3>
        <p>{index + 1} / {N}</p>
        <button type="button" className="pbtn" onClick={() => onPick(cur.id)}>이 제품군 선택하기</button>
      </div>

    </div>
  )
}
