import { NavLink, Route, Routes } from "react-router-dom";
import logo from "./admin/assets/ls-electric-logo.png";
import CustomerHome from "./pages/customer/CustomerHome";
import InquirePage from "./pages/customer/InquirePage";
import MyInquiries from "./pages/customer/MyInquiries";
import LangMenu from "./pages/customer/LangMenu";
import Onboarding from "./pages/customer/Onboarding";
import { useLangState } from "./lib/lang";
import "./pages/customer/shell.css";
import "./pages/customer/onboarding.css";

export default function App() {
  const { onboarded } = useLangState();
  if (!onboarded) return <Onboarding />; // 첫 방문(또는 [국가·언어 다시 고르기])에는 국가 확인과 언어 선택부터
  return (
    <>
      <header className="cs-top">
        <a href="/" className="cs-brand" aria-label="LS ELECTRIC 고객지원 홈">
          <img src={logo} alt="LS ELECTRIC" />
          <span>고객지원</span>
        </a>
        <nav className="cs-nav" aria-label="주 메뉴">
          <NavLink to="/" end>제품 · 상담</NavLink>
          <NavLink to="/inquire">문의 남기기</NavLink>
          <NavLink to="/my">내 문의</NavLink>
        </nav>
        <div className="cs-top-end">
          <LangMenu />
          <a href="/admin/" className="cs-staff">상담원용</a>
        </div>
      </header>
      <Routes>
        <Route path="/" element={<CustomerHome />} />
        <Route path="/inquire" element={<InquirePage />} />
        <Route path="/my" element={<MyInquiries />} />
      </Routes>
    </>
  );
}
