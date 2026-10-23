import { NavLink, Route, Routes } from "react-router-dom";
import logo from "./admin/assets/ls-electric-logo.png";
import CustomerHome from "./pages/customer/CustomerHome";
import MyInquiries from "./pages/customer/MyInquiries";
import "./pages/customer/shell.css";

export default function App() {
  return (
    <>
      <header className="cs-top">
        <a href="/" className="cs-brand" aria-label="LS ELECTRIC 고객지원 홈">
          <img src={logo} alt="LS ELECTRIC" />
          <span>고객지원</span>
        </a>
        <nav className="cs-nav" aria-label="주 메뉴">
          <NavLink to="/" end>제품 · 상담</NavLink>
          <NavLink to="/my">내 문의</NavLink>
        </nav>
        {/* 오른쪽 끝: 언어 선택 자리 (다국어 작업에서 붙인다) */}
        <div className="cs-top-end">
          <a href="/admin/" className="cs-staff">상담원용</a>
        </div>
      </header>
      <Routes>
        <Route path="/" element={<CustomerHome />} />
        <Route path="/my" element={<MyInquiries />} />
      </Routes>
    </>
  );
}
