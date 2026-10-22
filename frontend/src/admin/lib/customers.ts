// 고객 관리 공통: 이름표, 조치가 필요한 이유 3가지, 데이터 불러오기. 데이터는 크기 때문에 화면을 열 때 따로 불러온다.
import { useEffect, useState } from "react";
import type { Customer } from "@admin/data/customers-data";

export type { Customer };
export const SEGMENT_KO: Record<string, string> = { DISTRIBUTOR: "유통사", EPC: "EPC", END_USER: "최종 사용자", PANEL_BUILDER: "판넬 제작사", SYSTEM_INTEGRATOR: "시스템 통합사", UTILITY: "전력사" };
export const CATEGORY_KO: Record<string, string> = { TECH_SPEC: "기술 사양", DEFECT: "불량", INSTALL: "설치", MANUAL: "매뉴얼", FW_UPDATE: "펌웨어", COMPLIANCE: "인증", ORDER_LEAD: "납기", RETURN: "반품", QUOTE: "견적", WARRANTY: "보증" };
export const FAMILY_KO: Record<string, string> = { DRIVE: "인버터", PLC: "PLC", HMI: "HMI", LV_BREAKER: "저압 차단기", MV_EQUIP: "고압 설비", TRANSFORMER: "변압기", METER: "계량기", ESS: "ESS", PV: "태양광", UPS: "UPS", CONTROL: "제어" };
export const PRIORITY_KO: Record<string, string> = { P1: "위급", P2: "높음", P3: "보통", P4: "낮음" };
export const STATUS_KO: Record<string, string> = { CLOSED: "종료", RESOLVED: "해결", IN_PROGRESS: "진행 중", ESCALATED: "이관", WAITING_CUSTOMER: "고객 회신 대기", NEW: "신규" };

/** 국가 코드(US) → 깃발 이모지. */
export const flag = (code: string) => String.fromCodePoint(...[...code.toUpperCase()].map((ch) => 0x1f1e6 + ch.charCodeAt(0) - 65));

/** 대응이 필요한 사실 3가지(이슈 기준). 같은 고객이 여러 개에 해당할 수 있다. 예측이 아니라 확인된 사실만 쓴다. */
export type Reason = "urgent" | "breach" | "repeat";
export const hasReason = (c: Customer, r: Reason) => (r === "urgent" ? c.urgentN > 0 : r === "breach" ? c.breach >= 4 : c.fam[0][1] >= 4);
export const reasonsOf = (c: Customer): Reason[] => (["urgent", "breach", "repeat"] as Reason[]).filter((r) => hasReason(c, r));
/** 줄에 보여 줄 대표 사실 하나: 지연·임박 티켓(대응 버튼 있음) > 반복 문의 > 지연 이력(참고용). */
export const primaryReason = (c: Customer): Reason | undefined => (["urgent", "repeat", "breach"] as Reason[]).find((r) => hasReason(c, r)); // 대응 버튼이 있는 이유(지연·임박 티켓)를 먼저

/** 사실 한 줄(상세의 대응 항목). */
export function factText(c: Customer, r: Reason): string {
  const x = factParts(c, r);
  return `${x.title} · ${x.value}`;
}

/** 지연·임박 티켓 하나의 상태 문구: "5일 지연" / "26시간 남음". */
export const lateText = (u: Customer["urgent"][number]) => (u[4] >= u[3] ? `${Math.max(1, Math.round((u[4] - u[3]) / 24))}일 지연` : `${Math.max(1, Math.round(u[3] - u[4]))}시간 남음`);
export const isLate = (u: Customer["urgent"][number]) => u[4] >= u[3];

/** 기한을 넘긴 티켓 중 가장 오래 지연된 일수(없으면 0). */
export const maxLate = (c: Customer) => Math.max(0, ...c.urgent.filter(isLate).map((u) => Math.round((u[4] - u[3]) / 24)));
/** 7일 이상 지연이면 "심각" 단계로 색을 진하게 보여 준다. */
export const SEVERE_DAYS = 7;

/** 카드용 사실: 색(red 위급 · amber 주의 · blue 참고) + 짧은 이름 + 값. 문장으로 풀지 않고 이름과 값으로 나눠 쓴다. */
export function factParts(c: Customer, r: Reason): { tone: "severe" | "red" | "amber" | "blue"; title: string; value: string } {
  if (r === "urgent") {
    const late = c.urgent.filter(isLate);
    if (late.length) { const d = Math.max(1, maxLate(c)); return { tone: d >= SEVERE_DAYS ? "severe" : "red", title: `지연 티켓 ${late.length}건`, value: `최대 ${d}일 지연` }; }
    const soon = Math.min(...c.urgent.map((u) => u[3] - u[4]));
    return { tone: "amber", title: `임박 티켓 ${c.urgentN}건`, value: `${Math.max(1, Math.round(soon))}시간 남음` };
  }
  if (r === "breach") return { tone: "amber", title: `지연 이력 ${c.breach}회`, value: "최근 12개월" };
  return { tone: "blue", title: `${FAMILY_KO[c.fam[0][0]] || c.fam[0][0]} ${c.fam[0][1]}회 반복`, value: "최근 12개월" };
}

/**
 * 중점 관리 고객: ① PLATINUM·GOLD 고객 중 기한을 넘긴 진행 중 티켓이 있는 고객 ② 직접 지정한 고객.
 * 중요한 등급의 고객이 지금 약속을 못 지키고 있다는 뜻이다. STANDARD 는 직접 지정할 때만 들어간다.
 * 지연 이력·반복 문의·기한 임박은 편입 기준이 아니라 카드와 상세에 보여 주는 참고 정보다.
 * 대응 후 종결하면 목록에서 내려간다(직접 지정한 고객은 남는다).
 */
export type Focus = "issue" | "pinned" | null;
export function focusOf(c: Customer, rec?: { resolved?: boolean; pinned?: boolean }): Focus {
  if (c.tier !== "STANDARD" && c.urgent.some(isLate) && !rec?.resolved) return "issue";
  return rec?.pinned ? "pinned" : null;
}
/** 정렬 점수: 등급이 높고 SLA 초과가 많을수록 위로. */
export const score = (c: Customer) => c.urgentN * 5 + c.breach + (c.tier === "PLATINUM" ? 6 : c.tier === "GOLD" ? 2 : 0);
/** 마지막 문의로부터 지난 개월 수(데이터 기준일 2026-09-30). */
export const monthsSince = (c: Customer) => Math.floor((Date.UTC(2026, 8, 30) - Date.parse(c.last)) / (30 * 86400000));

// BACKEND: 고객 목록과 요약
// 필요(제안): GET /customers → Customer[]. 모양은 src/data/customers-data.ts 의 Customer 타입과 같다:
//   고객 정보(등급·국가·업종·거래 시작) + 12개월 문의 수 + SLA 초과 횟수 + 자주 문의한 제품군 + 기한을 넘겼거나 임박한 진행 중 티켓 + 최근 문의 5건.
// 지금: 학습 데이터(tickets.csv · ref/customers.csv)를 고객별로 미리 모아 둔 모의 데이터를 화면을 열 때 불러온다(합성 데이터, 기준일 2026-09-30).
export function useCustomers(): Customer[] | null {
  const [rows, setRows] = useState<Customer[] | null>(null);
  useEffect(() => { let on = true; import("@admin/data/customers-data").then((m) => on && setRows(m.customers)); return () => { on = false; }; }, []);
  return rows;
}
