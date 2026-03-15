// LabPilot AppLayout
// Design: Clinical Research Portal — deep navy sidebar, off-white content
// Space Grotesk headings, Inter body, JetBrains Mono for data

import { Link, useLocation } from "wouter";
import {
  FlaskConical,
  MessageSquare,
  BrainCircuit,
  Beaker,
  BarChart3,
  FolderOpen,
  Home,
  ChevronRight,
  Activity,
  PenSquare,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { API_BASE_URL } from "@/lib/api";

const navItems = [
  { path: "/", label: "Workspace", icon: Home },
  { path: "/conversations", label: "Conversations", icon: MessageSquare },
  { path: "/training", label: "Model Training", icon: BrainCircuit },
  { path: "/experiments", label: "Experiments", icon: Beaker },
  { path: "/evaluation", label: "Evaluation", icon: BarChart3 },
  { path: "/input", label: "Input", icon: PenSquare },
  { path: "/artifacts", label: "Artifacts", icon: FolderOpen },
];

interface AppLayoutProps {
  children: React.ReactNode;
  title?: string;
  subtitle?: string;
  actions?: React.ReactNode;
}

export default function AppLayout({ children, title, subtitle, actions }: AppLayoutProps) {
  const [location] = useLocation();

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* Sidebar */}
      <aside
        className="w-60 flex-shrink-0 flex flex-col"
        style={{ background: "oklch(0.175 0.04 255)" }}
      >
        {/* Logo */}
        <div className="flex items-center gap-2.5 px-5 py-5 border-b" style={{ borderColor: "oklch(0.28 0.04 255)" }}>
          <div
            className="w-8 h-8 rounded-lg flex items-center justify-center"
            style={{ background: "oklch(0.52 0.22 260)" }}
          >
            <FlaskConical className="w-4.5 h-4.5 text-white" />
          </div>
          <div>
            <div className="text-white font-semibold text-sm leading-tight" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
              LabPilot
            </div>
            <div className="text-xs" style={{ color: "oklch(0.55 0.04 255)" }}>
              AI Research Copilot
            </div>
          </div>
        </div>

        {/* Nav */}
        <nav className="flex-1 px-3 py-4 space-y-0.5 overflow-y-auto">
          <div className="text-xs font-medium px-2 mb-2" style={{ color: "oklch(0.45 0.04 255)", fontFamily: "'Inter', sans-serif", letterSpacing: "0.08em" }}>
            NAVIGATION
          </div>
          {navItems.map(({ path, label, icon: Icon }) => {
            const isActive = path === "/" ? location === "/" : location.startsWith(path);
            return (
              <Link key={path} href={path}>
                <div
                  className={cn(
                    "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-all duration-150 group relative",
                    isActive
                      ? "text-white"
                      : "text-[oklch(0.65_0.03_255)] hover:text-white hover:bg-[oklch(0.24_0.04_255)]"
                  )}
                  style={
                    isActive
                      ? { background: "oklch(0.52 0.22 260 / 0.2)", color: "white" }
                      : {}
                  }
                >
                  {isActive && (
                    <span
                      className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-5 rounded-r-full"
                      style={{ background: "oklch(0.52 0.22 260)" }}
                    />
                  )}
                  <Icon
                    className="w-4 h-4 flex-shrink-0"
                    style={isActive ? { color: "oklch(0.72 0.18 260)" } : {}}
                  />
                  <span style={{ fontFamily: "'Inter', sans-serif", fontWeight: isActive ? 500 : 400 }}>
                    {label}
                  </span>
                  {isActive && <ChevronRight className="w-3 h-3 ml-auto opacity-50" />}
                </div>
              </Link>
            );
          })}
        </nav>

        {/* Footer */}
        <div className="px-4 py-4 border-t" style={{ borderColor: "oklch(0.28 0.04 255)" }}>
          <div className="flex items-center gap-2">
            <div
              className="w-2 h-2 rounded-full"
              style={{ background: "oklch(0.72 0.18 160)", boxShadow: "0 0 6px oklch(0.72 0.18 160)" }}
            />
            <span className="text-xs" style={{ color: "oklch(0.55 0.04 255)", fontFamily: "'Inter', sans-serif" }}>
              Backend: Connected
            </span>
          </div>
          <div className="mt-1.5 flex items-center gap-1.5">
            <Activity className="w-3 h-3" style={{ color: "oklch(0.45 0.04 255)" }} />
            <span className="text-xs" style={{ color: "oklch(0.45 0.04 255)", fontFamily: "'JetBrains Mono', monospace" }}>
              {API_BASE_URL.replace(/^https?:\/\//, "")}
            </span>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Top header */}
        {(title || actions) && (
          <header className="flex items-center justify-between px-8 py-5 border-b border-border bg-card flex-shrink-0">
            <div>
              {title && (
                <h1
                  className="text-xl font-semibold text-foreground"
                  style={{ fontFamily: "'Space Grotesk', sans-serif" }}
                >
                  {title}
                </h1>
              )}
              {subtitle && (
                <p className="text-sm text-muted-foreground mt-0.5" style={{ fontFamily: "'Inter', sans-serif" }}>
                  {subtitle}
                </p>
              )}
            </div>
            {actions && <div className="flex items-center gap-3">{actions}</div>}
          </header>
        )}

        {/* Page content */}
        <main className="flex-1 overflow-y-auto">{children}</main>
      </div>
    </div>
  );
}
