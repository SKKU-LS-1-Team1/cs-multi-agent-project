// 제품 고장 → 증상 단계의 첨부(사진·영상·소리·QR). 화면 없이 검사할 수 있도록 판단 로직만 모았다.
// 목업이라 서버로 보내지 않고 브라우저 안에서만 미리보기한다.

export const MAX_PER_KIND = 5

export const KINDS = [
  { key: 'photo', label: '사진', hint: '고장 부위·표시창', accept: 'image/*', mime: 'image/', icon: 'photo', maxMB: 20,
    ext: ['jpg', 'jpeg', 'png', 'webp', 'heic', 'heif', 'gif'] },
  { key: 'video', label: '영상', hint: '작동 모습·이상 동작', accept: 'video/*', mime: 'video/', icon: 'video', maxMB: 200,
    ext: ['mp4', 'mov', 'm4v', 'webm', 'avi'] },
  { key: 'sound', label: '소리', hint: '이상한 소음 녹음', accept: 'audio/*', mime: 'audio/', icon: 'sound', maxMB: 50,
    ext: ['mp3', 'm4a', 'wav', 'aac', 'ogg', 'oga', 'flac'] },
  { key: 'qr', label: 'QR', hint: '제품에 붙은 QR 사진', accept: 'image/*', mime: 'image/', icon: 'qr', maxMB: 10,
    ext: ['jpg', 'jpeg', 'png', 'webp', 'heic', 'heif'] },
]

export const kindOf = (key) => KINDS.find((k) => k.key === key)

const extOf = (name) => (name.includes('.') ? name.split('.').pop().toLowerCase() : '')
export const sameFile = (a, b) => a.name === b.name && a.size === b.size && a.lastModified === b.lastModified

// 파일 형식이 맞는지. MIME을 알면 MIME으로만 본다(PDF를 사진으로 올리는 것을 막는다).
// 브라우저가 MIME을 못 알아볼 때(.heic·.m4a 등)만 확장자로 판단한다.
function typeOk(k, file) {
  if (file.type && file.type !== 'application/octet-stream') return file.type.startsWith(k.mime)
  return k.ext.includes(extOf(file.name))
}

// 받으면 null, 받지 않으면 사용자에게 보여 줄 이유. existing = 같은 종류로 이미 올린 파일들.
export function rejectReason(kindKey, file, existing) {
  const k = kindOf(kindKey)
  if (existing.length >= MAX_PER_KIND) return `${k.label}은 최대 ${MAX_PER_KIND}개까지 올릴 수 있어요`
  if (!typeOk(k, file)) return `${file.name}: ${k.label} 파일만 올릴 수 있어요`
  if (file.size === 0) return `${file.name}: 비어 있는 파일이에요`
  if (file.size > k.maxMB * 1048576) return `${file.name}: 크기가 너무 커요 (${k.label}은 ${k.maxMB}MB까지)`
  if (existing.some((x) => sameFile(x.file, file))) return `${file.name}: 이미 올린 파일이에요`
  return null
}

// 챗봇 상단 카드에 이어 줄 한 줄. 없으면 ''.
export function describe(items) {
  return KINDS.map((k) => [k.label, items.filter((x) => x.kind === k.key).length]).filter(([, n]) => n > 0)
    .map(([label, n]) => `${label} ${n}`).join(' · ')
}

// QR 사진에서 값을 읽는다. 브라우저가 BarcodeDetector를 지원할 때만 읽고, 아니면 'unsupported'.
// 읽은 값은 글자로만 보여 준다 — 링크로 열거나 자동으로 이동하지 않는다(QR에 악성 주소가 들어 있을 수 있다).
export async function readQr(file) {
  try {
    if (typeof window === 'undefined' || !('BarcodeDetector' in window)) return { status: 'unsupported' }
    const detector = new window.BarcodeDetector({ formats: ['qr_code'] })
    const bitmap = await createImageBitmap(file)
    const found = await detector.detect(bitmap)
    bitmap.close?.()
    if (!found.length) return { status: 'none' }
    // 제어 문자를 지우고 길이를 줄인다
    // eslint-disable-next-line no-control-regex
    const text = String(found[0].rawValue ?? '').replace(/[\u0000-\u001f\u007f]/g, ' ').trim().slice(0, 200)
    return text ? { status: 'read', text } : { status: 'none' }
  } catch {
    return { status: 'unsupported' }
  }
}
