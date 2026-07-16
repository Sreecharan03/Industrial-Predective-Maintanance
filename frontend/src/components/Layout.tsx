import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { api, auth } from "../lib/api";
import { CLASSES } from "../lib/ui";
import { Icon } from "./ui";

const NAV = [
  { to: "/overview", icon: "dashboard", label: "Overview" },
  ...Object.values(CLASSES).map((c) => ({
    to: `/fleet/${c.slug}`, icon: c.icon, label: c.label,
  })),
  { to: "/findings", icon: "fact_check", label: "Issues" },
  { to: "/alerts", icon: "notifications_active", label: "Alerts" },
  { to: "/reports", icon: "description", label: "Reports" },
  { to: "/copilot", icon: "auto_awesome", label: "Copilot" },
];

export default function Layout() {
  const nav = useNavigate();
  const [me, setMe] = useState<{ username: string; roles: string[] } | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    api.me().then(setMe).catch(() => nav("/login"));
  }, [nav]);

  const logout = () => {
    auth.clear();
    nav("/login");
  };

  return (
    <div className="min-h-screen flex">
      {/* Sidebar */}
      <aside
        className={`fixed z-30 inset-y-0 left-0 w-[248px] bg-card border-r border-line
                    flex flex-col transition-transform duration-300
                    ${open ? "translate-x-0" : "-translate-x-full"} lg:translate-x-0`}
      >
        <div className="h-16 flex items-center gap-2.5 px-5 border-b border-line">
          <span className="h-9 w-9 rounded-xl bg-brand-600 text-white grid place-items-center shadow-soft">
            <Icon name="graph_3" className="text-[20px]" />
          </span>
          <div className="leading-tight">
            <p className="font-extrabold tracking-tight">SenseMinds</p>
            <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-ink-muted">
              360 · Reliability
            </p>
          </div>
        </div>

        <nav className="flex-1 p-3 space-y-1 overflow-y-auto">
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              onClick={() => setOpen(false)}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold
                 transition-all duration-200 ${
                   isActive
                     ? "bg-brand-50 text-brand-700"
                     : "text-ink-soft hover:bg-canvas hover:text-ink"
                 }`
              }
            >
              {({ isActive }) => (
                <>
                  <Icon
                    name={n.icon}
                    className={`text-[20px] ${isActive ? "text-brand-600" : "text-ink-muted"}`}
                  />
                  {n.label}
                </>
              )}
            </NavLink>
          ))}
        </nav>

        <div className="p-3 border-t border-line">
          <div className="flex items-center gap-3 rounded-xl px-3 py-2.5">
            <span className="h-8 w-8 rounded-full bg-canvas border border-line grid place-items-center text-xs font-bold">
              {me?.username?.slice(0, 2).toUpperCase() ?? "··"}
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold truncate">{me?.username ?? "—"}</p>
              <p className="text-[11px] text-ink-muted truncate">
                {me?.roles?.[0]?.replace(/_/g, " ") ?? ""}
              </p>
            </div>
            <button onClick={logout} title="Sign out"
              className="text-ink-muted hover:text-crit transition-colors">
              <Icon name="logout" className="text-[18px]" />
            </button>
          </div>
        </div>
      </aside>

      {open && (
        <div className="fixed inset-0 z-20 bg-ink/20 lg:hidden" onClick={() => setOpen(false)} />
      )}

      {/* Main */}
      <div className="flex-1 lg:pl-[248px] min-w-0">
        <header className="h-16 sticky top-0 z-10 bg-canvas/85 backdrop-blur border-b border-line
                           flex items-center gap-3 px-5 lg:px-8">
          <button className="lg:hidden text-ink-soft" onClick={() => setOpen(true)}>
            <Icon name="menu" />
          </button>
          <div className="flex-1" />
          <span className="hidden sm:inline-flex items-center gap-1.5 text-xs font-semibold
                           text-ok bg-ok-soft ring-1 ring-ok-ring rounded-full px-2.5 py-1">
            <span className="h-1.5 w-1.5 rounded-full bg-ok" />
            Answers come only from real readings
          </span>
        </header>

        <main className="p-5 lg:p-8 max-w-[1400px] mx-auto space-y-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
