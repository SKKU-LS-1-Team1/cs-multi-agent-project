// 로그인 세션(화면만). 로그인한 사람의 고유번호(userId)를 이 브라우저 localStorage 에 기억한다.
// BACKEND: 인증
// 필요: POST /auth/login → { userId, name, role: "LEAD" | "MEMBER" }(세션·토큰), POST /auth/logout, GET /auth/me.
//        역할(팀장/팀원)에 따라 서버도 배정 API(PATCH /tickets/{id}/owner 등)를 팀장에게만 허용해야 한다.
// 지금: DB 없이 아래 시연 계정 4개(아이디·비밀번호·역할)를 코드에 두고 맞춰 본다. 역할(팀장/팀원)은 계정에 들어 있어, 로그인하면 자동으로 정해진다.
//       실제 서비스에서는 비밀번호를 화면 코드에 두지 않고 서버가 확인한다.
// 키: 사람은 바뀌지 않는 고유번호(userId, 예: EMP-0001)로 가리킨다. 이름·아이디(loginId)·직급은 그 번호에 붙은 정보다.
//      BACKEND: users 테이블의 기본키가 userId 이고, 문의의 담당자(owner)·이력의 작성자(actor)도 나중에 이름 대신 userId 로 바꾼다(lib/types.ts 참고).
const KEY = "cs-agent-admin-session-v1";

export type Role = "LEAD" | "MEMBER";
export type Account = { userId: string; loginId: string; password: string; name: string; role: Role };
/** 시연 계정. 팀장은 1명이고, 나머지는 팀원이다. */
export const ACCOUNTS: Account[] = [
  { userId: "EMP-0001", loginId: "doyeon.kim", password: "1234", name: "Doyeon Kim", role: "LEAD" },
  { userId: "EMP-0002", loginId: "minji.park", password: "1234", name: "Minji Park", role: "MEMBER" },
  { userId: "EMP-0003", loginId: "jun.lee", password: "1234", name: "Jun Lee", role: "MEMBER" },
  { userId: "EMP-0004", loginId: "hana.choi", password: "1234", name: "Hana Choi", role: "MEMBER" },
];
/** 아이디·비밀번호가 맞으면 세션을 시작하고 계정을 돌려준다. 틀리면 null. */
export function login(loginId: string, password: string): Account | null {
  const a = ACCOUNTS.find((x) => x.loginId === loginId.trim().toLowerCase() && x.password === password);
  if (a) startSession(a.userId);
  return a ?? null;
}

// BACKEND: Microsoft 로그인(Entra ID, OpenID Connect)
// 필요: 회사 Microsoft 계정으로 로그인(MSAL 등) → 서버가 토큰을 확인하고 { userId, name, role } 세션을 만든다.
//        팀장/팀원은 회사 그룹·앱 역할에서 가져오고, 이름·직급·부서는 Microsoft Graph 의 사용자 정보에서 읽는다.
//        userId 는 회사 계정의 사용자 고유값(objectId)과 연결한다.
// 지금: 이메일 앞부분(@ 앞)이 시연 계정의 아이디와 같으면 그 계정으로 들어간다. 실제 Microsoft 확인은 하지 않는다.
export function loginWithMicrosoft(email: string): Account | null {
  const local = email.trim().toLowerCase().split("@")[0];
  const a = ACCOUNTS.find((x) => x.loginId === local);
  if (a) startSession(a.userId);
  return a ?? null;
}

export const getSession = (): string | null => { try { return localStorage.getItem(KEY); } catch { return null; } };
/** 세션에 기억된 사람의 계정. 예전에 이름으로 저장된 세션도 찾아 준다. */
export const currentAccount = (): Account | undefined => { const s = getSession(); return ACCOUNTS.find((x) => x.userId === s) ?? ACCOUNTS.find((x) => x.name === s); };
export const startSession = (userId: string) => { try { localStorage.setItem(KEY, userId); } catch { /* 저장 못 하면 이번 방문에만 유효 */ } };
export const endSession = () => { try { localStorage.removeItem(KEY); } catch { /* 무시 */ } };
