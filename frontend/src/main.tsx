import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./i18n";
import "./index.css";

// apply the saved theme before first paint (falls back to the OS preference).
// Declaring our own dark scheme also stops browser "auto dark" from
// half-inverting pages, which made the top bar look inconsistent.
const savedTheme = localStorage.getItem("theme");
const dark = savedTheme ? savedTheme === "dark"
  : window.matchMedia("(prefers-color-scheme: dark)").matches;
document.documentElement.classList.toggle("dark", dark);

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
);
