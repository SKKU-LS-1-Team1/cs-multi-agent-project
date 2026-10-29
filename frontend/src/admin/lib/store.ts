// 단일 로컬 스토어. 레거시 app.js 처럼 문의 객체를 직접 수정하고 commit() 으로 저장·재렌더링한다.
import { useSyncExternalStore } from "react";
import type { ModalState, Ticket } from "./types";

const KEY = "cs-agent-admin-prototype-v1";

let saved: Ticket[] | null = null;
try {
  saved = JSON.parse(localStorage.getItem(KEY) || "null");
} catch {
  /* 저장소를 못 읽으면 빈 목록으로 시작 */
}

export const tickets: Ticket[] = Array.isArray(saved) ? saved.filter((t) => t?.source === "api") : [];

/** 화면 상태(저장하지 않음). */
export const ui = {
  ticketSync: "loading" as "loading" | "ready" | "error",
  ticketSyncError: "",
  completedTotal: null as number | null,
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
