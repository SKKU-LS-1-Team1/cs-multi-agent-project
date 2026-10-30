// 펌웨어 업데이트·고장은 문의 유형으로 받지 않는다. 최신 버전이 있어도 현장(24시간 가동, 정지 불가 등) 조건에 따라
// 올릴 수 있는지가 달라서, AI 상담이 요청을 알아보면 그 제품의 기술팀 연락처로 바로 잇는다.
// 펌웨어가 있는 제품은 제품 정보(info.json)에 펌웨어 이력이 있는 모델뿐이다 (13개). 그 밖의 모델에는 연락처를 주지 않는다.
import biz from '../data/biz.json'
import info from '../data/info.json'
import { families, getFamily, getProduct } from './catalog.js'

export const FW_MODELS = Object.keys(info).filter((code) => info[code].fw?.length > 0)
export const hasFirmware = (code) => FW_MODELS.includes(code)
const fwModelsOf = (family) => FW_MODELS.filter((code) => getProduct(code)?.family === family)

const FW = /펌웨어|firmware|\bf\/w\b/i
const UPDATE = /업데이트|업그레이드|올리|올려|올릴|적용|버전\s*업|update|upgrade|flash/i
const FAULT = /오류|에러|실패|고장|안\s*돼|안\s*되|멈|먹통|버그|error|fail|bug|crash/i
// 'fault' | 'update' | null. 업데이트하다 실패한 경우도 고장으로 본다.
export function firmwareIntent(text) {
  if (!FW.test(text)) return null
  return FAULT.test(text) ? 'fault' : UPDATE.test(text) ? 'update' : null
}

// 제품군마다 업데이트할 때 멈추는 것 (현장에서 바로 못 올리는 이유)
export const STOP = {
  UPS: 'UPS는 업데이트하는 동안 바이패스로 돌리거나 이중화된 쪽으로 넘겨야 해요. 그동안은 정전에 대비가 없어요.',
  PLC: 'PLC는 업데이트할 때 CPU를 정지(STOP)해야 해서 그동안 라인이 멈춰요. 프로그램 백업도 먼저 해 두어야 해요.',
  ESS: 'ESS는 업데이트할 때 운전을 멈추고 계통에서 분리해야 해요.',
  PV: '태양광 인버터는 업데이트하는 동안 발전이 멈춰요.',
  DRIVE: '인버터는 업데이트하는 동안 모터가 멈춰요. 연속 공정(펌프·팬)이면 정지 시간을 먼저 정해야 해요.',
  LV_BREAKER: '차단기 트립 유닛은 업데이트하는 동안 보호 기능이 빠져서, 운전 중에는 올리지 않아요.',
  HMI: 'HMI는 업데이트하는 동안 화면으로 설비를 보거나 조작할 수 없어요.',
  METER: '계측기는 업데이트하는 동안 계측 기록이 비어요.',
}

// 대화 키(모델 코드, fam:제품군, 단종·호환 문의는 legacy:제품군)로 모델·제품군을 찾는다. 제품군은 id나 이름으로 들어올 수 있다.
export function productOfKey(key) {
  const p = getProduct(key)
  if (p) return { model: p.code, family: p.family }
  const f = key?.startsWith('fam:') ? key.slice(4) : key?.startsWith('legacy:') ? key.slice(7) : null
  return { model: null, family: f ? (getFamily(f)?.id ?? families.find((x) => x.name === f)?.id ?? null) : null }
}

// 실제 부서 연락처는 제공 자료에 없다. 시연용 주소를 쓴다.
const demoMail = (code) => `${code.toLowerCase().replace(/_/g, '-')}@example.com`
export function firmwareContact(family) {
  const code = (family && biz.routing[family]?.FW_UPDATE?.primary) || 'GCS_L1'
  return { dept: biz.depts[code] ?? code, email: demoMail(code) }
}

const ASK = ['', '연락하실 때 아래를 함께 알려 주시면 빨리 도와드릴 수 있어요.', '- 현재 펌웨어 버전', '- 운전을 멈출 수 있는 시간 (없으면 "정지 불가")', '- 이중화나 바이패스 구성이 있는지']
const ASK_FAULT = ['', '연락하실 때 아래를 함께 알려 주시면 빨리 도와드릴 수 있어요.', '- 현재 펌웨어 버전과 올리려던 버전', '- 화면에 표시된 에러 코드나 증상', '- 업데이트 도구(로더) 버전']
const names = (codes) => codes.map((c) => getProduct(c).name).join(', ')

// { content, contact? } — contact 는 펌웨어가 있는 제품일 때만 준다.
export function firmwareReply({ model, family }, intent) {
  const fault = intent === 'fault'
  const head = fault
    ? ['펌웨어 오류나 업데이트 실패는 기술팀이 직접 확인해요. 전원을 껐다 켜거나 다시 올리기 전에 먼저 연락해 주세요.']
    : ['펌웨어 업데이트는 현장 조건에 따라 방법이 달라서 기술팀이 직접 안내해요.', '최신 버전이 나와 있어도, 전원을 끊을 수 없거나 24시간 돌아가야 하는 설비라면 바로 올리지 못할 수 있어요.']
  const tail = fault ? ASK_FAULT : ASK

  if (model && !hasFirmware(model)) {
    const p = getProduct(model)
    return { content: `${p.name}은(는) 펌웨어가 없는 제품이에요. 제품이 이상하면 '제품이 멈췄어요'에서 증상을 골라 해결 방법을 확인해 주세요.` }
  }
  if (model) {
    const why = !fault && STOP[family] ? [STOP[family]] : []
    return { content: [...head, ...why, ...tail].join('\n'), contact: firmwareContact(family) }
  }
  if (family) {
    const fw = fwModelsOf(family)
    const fam = getFamily(family).name
    if (!fw.length) return { content: `${fam}에는 펌웨어가 있는 제품이 없어요. 제품이 이상하면 '제품이 멈췄어요'에서 증상을 골라 해결 방법을 확인해 주세요.` }
    const why = !fault && STOP[family] ? [STOP[family]] : []
    return { content: [...head, ...why, `${fam} 중 펌웨어가 있는 제품은 ${names(fw)}예요.`, ...tail].join('\n'), contact: firmwareContact(family) }
  }
  return { content: [...head, `펌웨어가 있는 제품은 ${names(FW_MODELS)}예요.`, '어떤 제품인지 알려 주시면 그 제품 담당 기술팀으로 연결해 드려요.'].join('\n'), contact: firmwareContact(null) }
}
