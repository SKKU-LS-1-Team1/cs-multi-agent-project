// 고객 관리 공통: 서버 문의 기반 고객 요약·중점관리 기준·조회 상태.
import { useEffect, useState } from "react";
import { api } from "../../api/client";
import type { Customer } from "./customer-types";

export type { Customer };
export const SEGMENT_KO: Record<string, string> = { DISTRIBUTOR: "유통사", EPC: "EPC", END_USER: "최종 사용자", PANEL_BUILDER: "판넬 제작사", SYSTEM_INTEGRATOR: "시스템 통합사", UTILITY: "전력사" };
export const CATEGORY_KO: Record<string, string> = { TECH_SPEC: "기술 사양", DEFECT: "불량", INSTALL: "설치", MANUAL: "매뉴얼", FW_UPDATE: "펌웨어", COMPLIANCE: "인증", ORDER_LEAD: "납기", RETURN: "반품", QUOTE: "견적", WARRANTY: "보증" };
export const FAMILY_KO: Record<string, string> = { DRIVE: "인버터", PLC: "PLC", HMI: "HMI", LV_BREAKER: "저압 차단기", MV_EQUIP: "고압 설비", TRANSFORMER: "변압기", METER: "계량기", ESS: "ESS", PV: "태양광", UPS: "UPS", CONTROL: "제어" };
export const PRIORITY_KO: Record<string, string> = { P1: "위급", P2: "높음", P3: "보통", P4: "낮음" };
export const STATUS_KO: Record<string, string> = { CLOSED: "종료", RESOLVED: "해결", IN_PROGRESS: "진행 중", ESCALATED: "이관", WAITING_CUSTOMER: "고객 회신 대기", NEW: "신규", READY_FOR_REVIEW: "답변 검토", ON_HOLD: "보류", HUMAN_QUEUE: "사람 검토", ANALYSIS_PENDING: "분석 대기", APPROVED: "답변 발송", REJECTED: "반려" };

/** 국가 코드(US) → 깃발 이모지. */
export const flag = (code: string) => /^[A-Za-z]{2}$/.test(code) ? String.fromCodePoint(...[...code.toUpperCase()].map((ch) => 0x1f1e6 + ch.charCodeAt(0) - 65)) : "—";

/** 대응 판단에 사용하는 사실(이슈 기준). 같은 고객이 여러 개에 해당할 수 있다. 예측이 아니라 확인된 사실만 쓴다. */
export type Reason = "safety" | "urgent" | "breach" | "repeat";
export const hasReason = (c: Customer, r: Reason) => (r === "safety" ? c.safety.length > 0 : r === "urgent" ? c.urgentN > 0 : r === "breach" ? c.breach >= 4 : (c.fam[0]?.[1] ?? 0) >= 4);
export const reasonsOf = (c: Customer): Reason[] => (["safety", "urgent", "breach", "repeat"] as Reason[]).filter((r) => hasReason(c, r));
/** 줄에 보여 줄 대표 사실 하나: 지연·임박 문의(대응 버튼 있음) > 반복 문의 > 지연 이력(참고용). */
export const primaryReason = (c: Customer): Reason | undefined => (["safety", "urgent", "repeat", "breach"] as Reason[]).find((r) => hasReason(c, r)); // 대응 버튼이 있는 이유(지연·임박 문의)를 먼저

/** 사실 한 줄(상세의 대응 항목). */
export function factText(c: Customer, r: Reason): string {
  const x = factParts(c, r);
  return `${x.title} · ${x.value}`;
}

/** 지연·임박 문의 하나의 상태 문구: "5일 지연" / "26시간 남음". */
export const lateText = (u: Customer["urgent"][number]) => (u[4] >= u[3] ? `${Math.max(1, Math.round((u[4] - u[3]) / 24))}일 지연` : `${Math.max(1, Math.round(u[3] - u[4]))}시간 남음`);
export const isLate = (u: Customer["urgent"][number]) => u[4] >= u[3];

/** 기한을 넘긴 문의 중 가장 오래 지연된 일수(없으면 0). */
export const maxLate = (c: Customer) => Math.max(0, ...c.urgent.filter(isLate).map((u) => Math.round((u[4] - u[3]) / 24)));
/** 7일 이상 지연이면 "심각" 단계로 색을 진하게 보여 준다. */
export const SEVERE_DAYS = 7;

/** 카드용 사실: 색(red 위급 · amber 주의 · blue 참고) + 짧은 이름 + 값. 문장으로 풀지 않고 이름과 값으로 나눠 쓴다. */
export function factParts(c: Customer, r: Reason): { tone: "severe" | "red" | "amber" | "blue"; title: string; value: string } {
  if (r === "safety") return { tone: "red", title: `안전 검토 문의 ${c.safety.length}건`, value: "미완료" };
  if (r === "urgent") {
    const late = c.urgent.filter(isLate);
    if (late.length) { const d = Math.max(1, maxLate(c)); return { tone: d >= SEVERE_DAYS ? "severe" : "red", title: `지연 문의 ${late.length}건`, value: `최대 ${d}일 지연` }; }
    const soon = Math.min(...c.urgent.map((u) => u[3] - u[4]));
    return { tone: "amber", title: `임박 문의 ${c.urgentN}건`, value: `${Math.max(1, Math.round(soon))}시간 남음` };
  }
  if (r === "breach") return { tone: "amber", title: `지연 이력 ${c.breach}회`, value: "최근 12개월" };
  return { tone: "blue", title: `${FAMILY_KO[c.fam[0][0]] || c.fam[0][0]} ${c.fam[0][1]}회 반복`, value: "최근 12개월" };
}

/** 미완료 안전 문의 또는 GOLD·PLATINUM 지연 문의. 고객 대응 종결은 실제 문의 사유를 해제하지 않는다. */
export type Focus = "issue" | "pinned" | null;
export function focusOf(c: Customer, rec?: { resolved?: boolean; pinned?: boolean }): Focus {
  if (c.safety.length > 0 || (["GOLD", "PLATINUM"].includes(c.tier) && c.urgent.some(isLate))) return "issue";
  return rec?.pinned ? "pinned" : null;
}
/** 정렬 점수: 등급이 높고 SLA 초과가 많을수록 위로. */
export const score = (c: Customer) => c.urgentN * 5 + c.breach + (c.tier === "PLATINUM" ? 6 : c.tier === "GOLD" ? 2 : 0);
/** 마지막 문의로부터 지난 개월 수(현재 시각 기준). */
export const monthsSince = (c: Customer) => Math.floor((Date.now() - Date.parse(c.last)) / (30 * 86400000));

/** 서버 오류를 빈 목록/예시 고객으로 대체하지 않는다. 화면 진입 및 15초마다 갱신. */
export function useCustomers() {
  const [rows, setRows] = useState<Customer[] | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true, pending = false;
    const refresh = async () => {
      if (pending) return;
      pending = true;
      try { const data = await api.customers(); if (active) { setRows(data); setError(""); } }
      catch { if (active) { setError("고객 정보를 불러오지 못했습니다. 서버 연결을 확인해 주세요."); } }
      finally { pending = false; }
    };
    void refresh();
    const timer = setInterval(refresh, 15000);
    return () => { active = false; clearInterval(timer); };
  }, []);
  return { rows, error };
}
