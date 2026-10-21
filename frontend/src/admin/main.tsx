import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { startApiSync } from "./lib/api-sync";
import "./index.css";

startApiSync(); // 백엔드가 있으면 실제 문의로 바꾼다 (CSA-61)

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter basename="/admin">
      <App />
    </BrowserRouter>
  </React.StrictMode>,
);
