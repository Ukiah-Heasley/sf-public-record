import { BarChart3, CalendarDays, Search, ShieldCheck } from "lucide-react";
import Link from "next/link";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Dashboard", icon: BarChart3 },
  { href: "/search", label: "Search", icon: Search },
  { href: "/hearings", label: "Hearings", icon: CalendarDays }
];

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Link className="brand" href="/dashboard">
          <span className="brand-mark">SF</span>
          <span>SF Public Record</span>
        </Link>
        <nav className="nav" aria-label="Primary navigation">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            return (
              <Link className="nav-link" href={item.href} key={item.href}>
                <Icon size={18} />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>
        <div style={{ marginTop: 28 }}>
          <span className="badge accent">
            <ShieldCheck size={14} />
            local-first
          </span>
        </div>
      </aside>
      <div className="content">{children}</div>
    </div>
  );
}
