// 레거시 프로토타입의 문의/이벤트는 동적 필드가 많아 핵심 필드만 타입으로 고정하고 나머지는 열어 둔다.
export type Ev = { kind: string; text?: string; time?: string; createdAt?: string; actor?: string; id?: string; [k: string]: any };

export type Ticket = {
  id: string;
  title: string;
  product: string;
  country: string;
  company: string;
  type: string;
  priority: string;
  status: string;
  sla: string;
  owner: string; // BACKEND: 지금은 담당자 이름. DB 에서는 담당자의 userId(고유번호)로 바꾼다.
  language: string;
  stage: number; // 0 진행, 5 완료
  risk: boolean;
  events: Ev[];
  draft: string;
  files: string[];
  reviewed: boolean;
  [k: string]: any;
};

export type Person = {
  name: string;
  /** 계정 고유번호(키). 로그인 계정(lib/auth.ts)과 같은 값이다. */
  userId?: string;
  /** 직급(팀장은 직책). 화면에서 이름 옆에 작게 보인다. */
  rank?: string;
  department: string;
  capacity: number;
  available: boolean;
};

export type ModalState = { type: string; props?: Record<string, any> } | null;
