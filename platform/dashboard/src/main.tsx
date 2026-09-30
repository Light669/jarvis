import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";
import { captureToken } from "./lib/api";

captureToken();
window.addEventListener("hashchange", () => {
  if (/token=/.test(location.hash)) {
    captureToken();
    location.reload();
  }
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
