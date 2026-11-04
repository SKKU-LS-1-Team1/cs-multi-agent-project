// 처리 단계(접수·확인 → 전문부서 → 답변 작성 → 발송 → 완료): 문의 상세의 진행 막대와 문의 목록의 "3/5 전문부서" 표시가 같이 쓴다.
import { expertPhase, expertReviewModal, informationAssessment, informationSummary, latestCustomerReply, pendingCustomerInfo, requiredInformation, waitingReviews } from "./logic";
import { openModal } from "./store";
import type { Ticket } from "./types";
import { investigationTask } from "./investigation";

export type StepState = "done" | "current" | "waiting" | "todo" | "optional";
export type Step = { key: string; label: string; sub: string; state: StepState; action?: { label: string; run: () => void } };
export function flowSteps(t: Ticket): Step[] {
  const items = informationAssessment(t), req = requiredInformation(t).length, reply = latestCustomerReply(t);
  const pending = waitingReviews(t).length + (t.legacyReviewPending ? 1 : 0), gotExpert = t.events.some((e) => e.kind === "expert");
  const missing = items.filter((x) => !["provided", "confirmed"].includes(x.status)).length, needsCheck = t.customerRequestStatus === "received" && reply && req > 0 && reply.id !== t.reviewedReplyKey;
  const writingExpert = t.activeComposer === "expert", reviewing = expertPhase(t) === "review";
  // 회신 수신은 검토 완료가 아니다. Copilot과 같은 후속 업무 판정을 사용한다.
  const specialistTask = investigationTask(t);
  const specialistActive = !!specialistTask && t.customerRequestStatus !== "waiting";
  const writing = !writingExpert && !!t.draft && t.purpose === "answer";
  const done = t.stage === 5, analysisReady = t.source !== "api" || t.analysisReady;
  const steps: Step[] = [
    { key: "intake", label: "접수·확인", sub: !analysisReady ? t.status : !req ? "분석 완료 · 추가 자료 불필요" : t.customerRequestStatus === "none" && missing ? `자료 필요 ${missing}건` : informationSummary(t), state: !analysisReady ? "current" : !req || !missing ? "done" : t.customerRequestStatus === "waiting" ? "waiting" : "current",
      action: needsCheck && !done ? { label: "수신 자료 확인", run: () => openModal("review-customer", { id: t.id }) } : undefined },
    { key: "expert", label: "전문부서", sub: writingExpert ? "요청서 작성 중" : pending ? `회신 대기 ${pending}건` : specialistActive ? specialistTask.title : reviewing ? "회신 도착 · 검토 필요" : gotExpert ? "회신 반영 완료" : "요청 없음 (선택)", state: writingExpert || pending || specialistActive || reviewing ? "current" : gotExpert ? "done" : "optional",
      action: pending && !done ? { label: "회신 등록", run: () => openModal("expert-receive", { id: t.id }) } : reviewing ? { label: "회신 검토", run: () => { const m = expertReviewModal(t); if (m) openModal(m[0], m[1]); } } : undefined },
    { key: "answer", label: "답변 작성", sub: t.sent ? "작성 완료" : writing ? (t.reviewed ? "발송 준비 완료" : "영어 초안 검토 중") : "작성 전", state: t.sent ? "done" : writing ? "current" : "todo" },
    { key: "send", label: "발송", sub: t.sent ? (t.customerOutcome === "resolved" ? "해결 회신 수신" : t.customerOutcome === "provided" ? "정보 확인 회신" : "발송 완료") : "대기", state: t.sent ? "done" : "todo",
      action: reply ? { label: "고객 회신 보기", run: () => openModal("customer-reply", { id: t.id }) } : undefined },
    { key: "done", label: "완료", sub: done ? "처리 완료" : "대기", state: done ? "done" : "todo" },
  ];
  if (done) steps.forEach((x) => (x.state = "done"));
  else if (!t.owner) { // 아직 배정 전인 문의는 1단계(접수·확인)에만 있다: 담당자가 맡아야 다음 단계가 시작된다
    steps.forEach((x, i) => (x.state = i === 0 ? "current" : "todo"));
    steps[0].sub = "배정 대기";
  }
  else if (!steps.some((x) => x.state === "current")) { const i = steps.findIndex((x) => x.state === "todo"); if (i >= 0) steps[i].state = "current"; }
  // 병행 중인 단계가 둘 이상이면 하나만 "지금 단계"로 펼치고(답변 작성 중이면 답변 작성), 나머지는 "대기"로 접는다.
  const live = steps.map((x, i) => (x.state === "current" ? i : -1)).filter((i) => i >= 0);
  if (live.length > 1) {
    // 전문부서 회신을 기다리는 중이면 그 단계가 지금 단계(답변 초안이 있어도 회신 전에는 발송하지 못한다).
    // 고객 정보가 끝나지 않았으면 그 단계가 먼저다(고객 정보 확인 → 전문부서). 그 외에는 아래 규칙.
    const focus = (pendingCustomerInfo(t) > 0 ? live.find((i) => steps[i].key === "intake") : undefined) ?? live.find((i) => steps[i].key === (pending || writingExpert || specialistActive || reviewing ? "expert" : "answer")) ?? live[0];
    live.forEach((i) => { if (i !== focus) steps[i].state = steps[i].key === "expert" ? "waiting" : "todo"; });
    if (pending && steps[focus].key === "expert") steps[focus].state = "waiting";
  }
  if (pending && !done) { const e = steps.find((x) => x.key === "expert"); if (e) e.state = "waiting"; } // 회신을 기다리는 단계는 항상 시계 아이콘
  return steps;
}

/** 처리 단계 이름(진행 순서). 문의 목록의 단계 필터가 쓴다. */
export const STEP_LABELS = ["접수·확인", "전문부서", "답변 작성", "발송", "완료"] as const;

/** 문의 목록용 현재 단계: "지금 몇 번째 단계인지"(1~5)와 이름. 병행 단계는 flowSteps 가 정한 "지금 단계" 하나를 쓴다. */
export function currentStep(t: Ticket): { index: number; total: number; label: string; waiting: boolean; done: boolean; phase?: string } {
  const steps = flowSteps(t);
  const i = steps.findIndex((x) => x.state === "current" || x.state === "waiting");
  if (t.stage === 5 || i < 0) return { index: steps.length, total: steps.length, label: steps[steps.length - 1].label, waiting: false, done: true };
  return { index: i + 1, total: steps.length, label: steps[i].label, waiting: steps[i].state === "waiting", done: false, phase: steps[i].key === "expert" ? { writing: "요청서 작성", waiting: "회신 대기", review: "회신 검토" }[expertPhase(t) as string] : undefined };
}
