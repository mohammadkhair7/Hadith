import { FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { api, setTokens } from "../api";

export default function Login() {
  const { t } = useTranslation();
  const nav = useNavigate();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      const t = await api<any>(`/auth/${mode}`, {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      setTokens(t);
      nav("/");
    } catch (err: any) {
      setError(err.message);
    }
  }

  return (
    <div className="max-w-sm mx-auto mt-12 bg-white rounded-2xl shadow-lg p-8 border-t-4 border-islamic-gold">
      <h1 className="text-xl font-bold text-center mb-6 text-deep-teal">
        {mode === "login" ? t("login") : t("register")}
      </h1>
      <form onSubmit={submit} className="space-y-4">
        <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
          placeholder={t("email")} dir="ltr"
          className="w-full border rounded-lg px-4 py-2.5 focus:border-islamic-teal outline-none" />
        <input type="password" required minLength={8} value={password}
          onChange={(e) => setPassword(e.target.value)} placeholder={t("password")} dir="ltr"
          className="w-full border rounded-lg px-4 py-2.5 focus:border-islamic-teal outline-none" />
        {error && <div className="text-red-600 text-sm">{error}</div>}
        <button className="w-full bg-islamic-teal text-white rounded-lg py-2.5 hover:bg-deep-teal transition-colors font-bold">
          {mode === "login" ? t("login") : t("register")}
        </button>
      </form>
      <button
        onClick={() => setMode(mode === "login" ? "register" : "login")}
        className="w-full text-center text-sm text-islamic-teal mt-4 hover:underline">
        {mode === "login" ? t("register") : t("login")}
      </button>
    </div>
  );
}
