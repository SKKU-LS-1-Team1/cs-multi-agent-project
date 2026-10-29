import { Navigate, Route, Routes } from "react-router-dom";
import AdminLayout from "./components/admin/AdminLayout";
import Overview from "./pages/Overview";
import Tickets from "./pages/Tickets";
import TicketDetail from "./pages/TicketDetail";
import Customers from "./pages/Customers";
import CustomerDetail from "./pages/CustomerDetail";
import Knowledge from "./pages/Knowledge";
import Mailbox from "./pages/Mailbox";
import NotFound from "./pages/NotFound";
import Login from "./pages/Login";
import { currentAccount } from "./lib/auth";

export default function App() {
  if (!currentAccount()) return <Login />; // 로그인하지 않았으면 로그인 화면만 보인다
  return (
    <Routes>
      <Route element={<AdminLayout />}>
        <Route index element={<Overview />} />
        <Route path="dashboard" element={<Navigate to="/" replace />} />
        <Route path="collab" element={<Overview />} />
        <Route path="resources" element={<Overview />} />
        <Route path="tickets" element={<Tickets />} />
        <Route path="tickets/:ticketId" element={<TicketDetail />} />
        <Route path="customers" element={<Customers />} />
        <Route path="customers/:customerId" element={<CustomerDetail />} />
        <Route path="knowledge" element={<Knowledge />} />
        <Route path="mail" element={<Mailbox />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
