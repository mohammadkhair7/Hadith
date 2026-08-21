import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import Home from "./pages/Home";
import Search from "./pages/Search";
import Books from "./pages/Books";
import Reader from "./pages/Reader";
import Passage from "./pages/Passage";
import Subjects from "./pages/Subjects";
import Narrators from "./pages/Narrators";
import Analytics from "./pages/Analytics";
import Timeline from "./pages/Timeline";
import Login from "./pages/Login";
import Account from "./pages/Account";
import AdminStatus from "./pages/AdminStatus";
import AdminNarrators from "./pages/AdminNarrators";
import AdminEmbeddings from "./pages/AdminEmbeddings";
import AdminTranslations from "./pages/AdminTranslations";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Home />} />
        <Route path="/search" element={<Search />} />
        <Route path="/books" element={<Books />} />
        <Route path="/read/:editionId" element={<Reader />} />
        <Route path="/passage/:passageId" element={<Passage />} />
        <Route path="/subjects" element={<Subjects />} />
        {/* اسأل الموسوعة now lives as a tab inside the unified Search page */}
        <Route path="/ask" element={<Navigate to="/search?tab=ask" replace />} />
        <Route path="/narrators" element={<Narrators />} />
        <Route path="/analytics" element={<Analytics />} />
        <Route path="/timeline" element={<Timeline />} />
        <Route path="/login" element={<Login />} />
        <Route path="/account" element={<Account />} />
        <Route path="/admin" element={<AdminStatus />} />
        <Route path="/admin/narrators" element={<AdminNarrators />} />
        <Route path="/admin/embeddings" element={<AdminEmbeddings />} />
        <Route path="/admin/translations" element={<AdminTranslations />} />
      </Route>
    </Routes>
  );
}
