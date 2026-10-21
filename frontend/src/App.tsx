import { Link, Route, Routes } from "react-router-dom";
import CustomerHome from "./pages/customer/CustomerHome";
import MyInquiries from "./pages/customer/MyInquiries";

export default function App() {
  return (
    <>
      <nav style={{ display: "flex", gap: 16, padding: 12, borderBottom: "1px solid #ddd" }}>
        <Link to="/">고객 화면</Link>
        <Link to="/my">내 문의 내역</Link>
        <a href="/admin/">관리자 Workspace</a>
      </nav>
      <Routes>
        <Route path="/" element={<CustomerHome />} />
        <Route path="/my" element={<MyInquiries />} />
      </Routes>
    </>
  );
}
