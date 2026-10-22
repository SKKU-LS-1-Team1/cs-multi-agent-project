// 단일 로컬 스토어. 레거시 app.js 처럼 티켓 객체를 직접 수정하고 commit() 으로 저장·재렌더링한다.
import { useSyncExternalStore } from "react";
import type { ModalState, Ticket } from "./types";

const KEY = "cs-agent-admin-prototype-v1";

const initial = [
  { id: "CSV1-000050", title: "iS7 운전 직후 E.OC 트립", product: "iS7 75kW", country: "Australia", company: "Atlas Engineering", type: "불량", priority: "P2", status: "검토 중", sla: "1h 20m", owner: "Doyeon Kim", language: "English", stage: 0, risk: false },
  { id: "CSV1-000051", title: "H100 통신 설정 문의", product: "H100 22kW", country: "Germany", company: "Nordwerk GmbH", type: "설치", priority: "P3", status: "미배정", sla: "3h 40m", owner: "", language: "English", stage: 0, risk: false },
  { id: "CSV1-000052", title: "PLC 펌웨어 업데이트 요청", product: "XGI CPU", country: "India", company: "Prakash Automation", type: "펌웨어", priority: "P3", status: "추가정보 수신", sla: "6h", owner: "Minji Park", language: "English", stage: 2, risk: false },
  { id: "CSV1-000053", title: "인버터 과열 알람 반복", product: "S100 7.5kW", country: "Vietnam", company: "Mekong Systems", type: "불량", priority: "P2", status: "전문부서 검토", sla: "초과 34m", owner: "Jun Lee", language: "English", stage: 3, risk: true },
  { id: "CSV1-000054", title: "차단기 기술문서 요청", product: "MCCB 100AF", country: "United States", company: "Westline Electric", type: "문서 요청", priority: "P4", status: "답변 준비", sla: "8h", owner: "Hana Choi", language: "English", stage: 4, risk: false },
  { id: "CSV1-000055", title: "정격 전압 사양 확인", product: "ACB 2000A", country: "Spain", company: "Iberia Controls", type: "사양", priority: "P4", status: "답변 준비", sla: "10h", owner: "Hana Choi", language: "English", stage: 4, risk: false },
  { id: "CSV1-000056", title: "제품 보증 기간 확인", product: "H100 22kW", country: "Germany", company: "Nordwerk GmbH", type: "보증", priority: "P3", status: "검토 중", sla: "12h", owner: "Doyeon Kim", language: "English", stage: 0, risk: false },
  { id: "CSV1-000057", title: "S100 영문 매뉴얼 요청", product: "S100 7.5kW", country: "Australia", company: "Southern Drives", type: "문서 요청", priority: "P4", status: "완료", sla: "기한 내 완료", owner: "Minji Park", language: "English", stage: 5, risk: false },
];

let saved: Ticket[] | null = null;
try {
  saved = JSON.parse(localStorage.getItem(KEY) || "null");
} catch {
  /* 저장소를 못 읽으면 초기 데이터로 시작 */
}

export const tickets: Ticket[] = Array.isArray(saved) && saved.length ? saved : initial.map((t) => ({ ...t, events: [], draft: "", files: [], reviewed: false }) as Ticket);

/** 화면 상태(저장하지 않음). */
export const ui = {
  filter: "내 담당",
  query: "",
  status: "",
  priority: "",
  product: "",
  listOwner: "",
  queueScope: "내 담당",
  tab: "문의·답변",
  evidenceOpen: false,
  department: "전체 부서",
  departmentFilter: "전체",
  knowledge: 0,
  knowledgeTab: "해결 사례",
  kquery: "",
  completedFilter: "전체 기록",
  completedTicket: null as string | null,
  modal: null as ModalState,
};

let version = 0;
const subs = new Set<() => void>();
let beforeCommit: (() => void) | null = null;
export const onBeforeCommit = (fn: () => void) => (beforeCommit = fn);

export function save() {
  try {
    localStorage.setItem(KEY, JSON.stringify(tickets));
  } catch {
    /* 저장 실패는 화면 동작에 영향을 주지 않는다 */
  }
}
export function commit() {
  beforeCommit?.();
  save();
  version++;
  subs.forEach((f) => f());
}
export function setUi(patch: Partial<typeof ui>) {
  Object.assign(ui, patch);
  version++;
  subs.forEach((f) => f());
}
export function useStore() {
  return useSyncExternalStore(
    (f) => {
      subs.add(f);
      return () => subs.delete(f);
    },
    () => version,
  );
}
export const openModal = (type: string, props: Record<string, any> = {}) => setUi({ modal: { type, props } });
export const closeModal = () => setUi({ modal: null });
export const findTicket = (id?: string | null) => tickets.find((t) => t.id === id);
export function resetLocalData() {
  try {
    localStorage.removeItem(KEY);
  } catch {
    /* noop */
  }
  location.reload();
}
