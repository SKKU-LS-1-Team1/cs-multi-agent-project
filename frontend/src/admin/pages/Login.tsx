// 로그인 화면(화면만). 아이디·비밀번호를 입력하면 계정에 정해진 역할(팀장/팀원)로 들어간다.
// BACKEND: 인증은 lib/auth.ts 의 주석 참고(로그인 API 와 역할 확인이 필요하다).
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Lock, User } from "lucide-react";
import { Button } from "@admin/components/ui/button";
import { Input } from "@admin/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@admin/components/ui/dialog";
import { login, loginWithMicrosoft } from "@admin/lib/auth";
import logo from "@admin/assets/ls-electric-logo-reverse.png";

/** Microsoft 로고(네 칸). 공식 색을 그대로 쓴다. */
const MsLogo = ({ size = 20 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 21 21" aria-hidden><rect x="1" y="1" width="9" height="9" fill="#f25022" /><rect x="11" y="1" width="9" height="9" fill="#7fba00" /><rect x="1" y="11" width="9" height="9" fill="#00a4ef" /><rect x="11" y="11" width="9" height="9" fill="#ffb900" /></svg>
);

export default function Login() {
  const nav = useNavigate();
  const [id, setId] = useState(""), [pw, setPw] = useState(""), [error, setError] = useState("");
  const [ms, setMs] = useState(false), [email, setEmail] = useState(""), [msError, setMsError] = useState("");
  const enterMs = () => {
    if (loginWithMicrosoft(email)) { nav("/", { replace: true }); window.location.reload(); }
    else setMsError("이 Microsoft 계정을 찾을 수 없습니다. 다시 입력해 주세요.");
  };
  const submit = () => {
    if (login(id, pw)) { nav("/", { replace: true }); window.location.reload(); } // 첫 화면(업무 현황)으로 가고, 로그인한 사람을 앱 전체가 새로 읽도록 다시 불러온다
    else setError("아이디 또는 비밀번호가 올바르지 않습니다.");
  };
  return (
    <div className="grid min-h-dvh grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)] bg-[linear-gradient(172deg,#04337a_0%,#0a4a98_36%,#1f77c4_72%,#7cc2ec_100%)] text-white max-[900px]:grid-cols-1">
      <section className="grid place-items-center px-14 max-[900px]:hidden">
        <div className="w-full max-w-[340px]">
          <img src={logo} alt="LS ELECTRIC" width={2029} height={322} style={{ display: "block", width: "100%", height: "auto" }} />
          <p className="mt-4 text-center text-base font-medium tracking-wide text-white/75">글로벌 고객지원</p>
        </div>
      </section>

      <main className="m-3 grid place-items-center rounded-[28px] bg-background px-8 py-12 text-foreground max-[900px]:m-0 max-[900px]:rounded-none">
        <form className="grid w-full max-w-[400px] gap-7" onSubmit={(e) => { e.preventDefault(); submit(); }}>
          <header className="grid gap-2">
            <h1 className="text-[32px] font-bold tracking-tight">로그인</h1>
            <p className="text-muted-foreground">회사 계정으로 로그인하세요.</p>
          </header>

          <div className="grid gap-5">
            <Button type="button" variant="outline" size="lg" className="h-12 w-full gap-3 bg-card shadow-card" onClick={() => { setEmail(""); setMsError(""); setMs(true); }}><MsLogo />Microsoft 계정으로 로그인</Button>
            <div className="flex items-center gap-3 text-xs text-muted-foreground"><span className="h-px flex-1 bg-border" />또는<span className="h-px flex-1 bg-border" /></div>
          </div>

          <div className="grid gap-4">
            <label className="grid gap-2 text-sm"><span className="text-muted-foreground">아이디</span>
              <span className="relative"><User className="pointer-events-none absolute left-4 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
                <Input aria-label="아이디" autoFocus autoComplete="username" className="h-12 rounded-full bg-card pl-11 shadow-card" placeholder="아이디" value={id} onChange={(e) => { setId(e.target.value); setError(""); }} />
              </span>
            </label>
            <label className="grid gap-2 text-sm"><span className="text-muted-foreground">비밀번호</span>
              <span className="relative"><Lock className="pointer-events-none absolute left-4 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
                <Input type="password" aria-label="비밀번호" autoComplete="current-password" className="h-12 rounded-full bg-card pl-11 shadow-card" placeholder="비밀번호" value={pw} onChange={(e) => { setPw(e.target.value); setError(""); }} />
              </span>
            </label>
            {error && <p role="alert" className="px-1 text-sm text-destructive">{error}</p>}
          </div>

          <Button type="submit" size="lg" className="h-12 w-full" disabled={!id.trim() || !pw}>로그인</Button>

        </form>
      </main>

      <Dialog open={ms} onOpenChange={setMs}>
        <DialogContent className="max-w-[420px] gap-6 p-8">
          <DialogHeader className="gap-5">
            <span className="flex items-center gap-2 text-[15px] font-semibold text-[#5e5e5e]"><MsLogo size={22} />Microsoft</span>
            <DialogTitle className="text-2xl font-semibold">로그인</DialogTitle>
          </DialogHeader>
          <form className="grid gap-5" onSubmit={(e) => { e.preventDefault(); enterMs(); }}>
            <label className="grid gap-1.5 text-sm"><span className="sr-only">회사 이메일</span>
              <Input aria-label="회사 이메일" type="email" autoFocus className="h-11 rounded-md border-0 border-b border-[#8a8886] bg-transparent px-0 text-base shadow-none focus-visible:ring-0" placeholder="이메일 주소" value={email} onChange={(e) => { setEmail(e.target.value); setMsError(""); }} />
            </label>
            {msError && <p role="alert" className="text-sm text-destructive">{msError}</p>}
            <div className="flex justify-end gap-2"><Button type="button" variant="ghost" onClick={() => setMs(false)}>취소</Button><Button type="submit" className="min-w-24 rounded-md bg-[#0067b8] hover:bg-[#005da6]" disabled={!email.trim()}>다음</Button></div>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
