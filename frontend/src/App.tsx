import { Link, Route, Routes } from "react-router-dom";
import CustomerHome from "./pages/customer/CustomerHome";
import MyInquiries from "./pages/customer/MyInquiries";
import WorkList from "./pages/admin/WorkList";
import ReviewPage from "./pages/admin/ReviewPage";
import DeptDashboard from "./pages/admin/DeptDashboard";

export default function App() {
  return (
    <>
      <nav style={{ display: "flex", gap: 16, padding: 12, borderBottom: "1px solid #ddd" }}>
        <Link to="/">고객 화면</Link>
        <Link to="/my">내 문의 내역</Link>
        <Link to="/admin">상담원 작업 목록</Link>
        <Link to="/admin/dashboard">부서별 대시보드</Link>
      </nav>
      <Routes>
        <Route path="/" element={<CustomerHome />} />
        <Route path="/my" element={<MyInquiries />} />
        <Route path="/admin" element={<WorkList />} />
        <Route path="/admin/tickets/:ticketId" element={<ReviewPage />} />
        <Route path="/admin/dashboard" element={<DeptDashboard />} />
      </Routes>
    </>
  );
}
