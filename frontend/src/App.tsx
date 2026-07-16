import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import AssetDetail from "./pages/AssetDetail";
import Copilot from "./pages/Copilot";
import Findings from "./pages/Findings";
import Alerts from "./pages/Alerts";
import Fleet from "./pages/Fleet";
import Login from "./pages/Login";
import Overview from "./pages/Overview";
import Reports from "./pages/Reports";
import { auth } from "./lib/api";

function Protected({ children }: { children: JSX.Element }) {
  return auth.token ? children : <Navigate to="/login" replace />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<Protected><Layout /></Protected>}>
        <Route path="/overview" element={<Overview />} />
        <Route path="/fleet/:slug" element={<Fleet />} />
        <Route path="/asset/:unit" element={<AssetDetail />} />
        <Route path="/findings" element={<Findings />} />
        <Route path="/alerts" element={<Alerts />} />
        <Route path="/reports" element={<Reports />} />
        <Route path="/copilot" element={<Copilot />} />
      </Route>
      <Route path="*" element={<Navigate to="/overview" replace />} />
    </Routes>
  );
}
