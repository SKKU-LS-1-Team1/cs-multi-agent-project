import { Navigate, Route, Routes } from "react-router-dom";
import AdminLayout from "./components/admin/AdminLayout";
import Overview from "./pages/Overview";
import Tickets from "./pages/Tickets";
import TicketDetail from "./pages/TicketDetail";
import Knowledge from "./pages/Knowledge";
import NotFound from "./pages/NotFound";

export default function App() {
  return (
    <Routes>
      <Route element={<AdminLayout />}>
        <Route index element={<Overview />} />
        <Route path="dashboard" element={<Navigate to="/" replace />} />
        <Route path="collab" element={<Overview />} />
        <Route path="resources" element={<Overview />} />
        <Route path="tickets" element={<Tickets />} />
        <Route path="tickets/:ticketId" element={<TicketDetail />} />
        <Route path="knowledge" element={<Knowledge />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
