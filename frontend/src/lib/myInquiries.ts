// 이 브라우저에서 낸 문의 목록 (CSA-61). 로그인이 아직 없어 내 문의 내역은 여기 남긴 ticket_id 로 찾는다.
// 로그인이 생기면 customer_id 기준 조회 API 로 바꾼다.
export type MyInquiry = { ticket_id: string; thread_ref: string; subject: string; submitted_at: string; notify_email?: string };

const KEY = "cs-agent-my-inquiries-v1";

export function myInquiries(): MyInquiry[] {
  try {
    const saved = JSON.parse(localStorage.getItem(KEY) || "[]");
    return Array.isArray(saved) ? saved : [];
  } catch {
    return [];
  }
}

export function rememberInquiry(item: Omit<MyInquiry, "submitted_at">) {
  const rest = myInquiries().filter((x) => x.ticket_id !== item.ticket_id);
  try {
    localStorage.setItem(KEY, JSON.stringify([{ ...item, submitted_at: new Date().toISOString() }, ...rest]));
  } catch {
    /* 저장하지 못해도 문의 제출은 끝났다 */
  }
}

// 알림 받을 메일을 고쳤을 때 이 브라우저의 기록도 같이 고친다
export function setInquiryEmail(ticket_id: string, notify_email: string) {
  try {
    localStorage.setItem(KEY, JSON.stringify(myInquiries().map((x) => (x.ticket_id === ticket_id ? { ...x, notify_email } : x))));
  } catch {
    /* 저장하지 못해도 화면에서는 바뀐다 */
  }
}

export const newThreadRef = () => `web-${crypto.randomUUID()}`;
