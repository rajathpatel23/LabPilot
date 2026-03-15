// LabPilot Artifacts / Output Explorer
// Design: Clinical Research Portal
// File browser with type icons, JSON preview, filter by type

import { useState } from "react";
import AppLayout from "@/components/AppLayout";
import { mockArtifacts } from "@/lib/mockData";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  FileJson,
  ImageIcon,
  Package,
  FolderOpen,
  Search,
  Eye,
  Download,
  X,
  File,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

type ArtifactType = "all" | "json" | "plot" | "model";

const TYPE_ICONS: Record<string, React.ElementType> = {
  json: FileJson,
  plot: ImageIcon,
  model: Package,
};

const TYPE_COLORS: Record<string, string> = {
  json: "oklch(0.52 0.22 260)",
  plot: "oklch(0.72 0.18 160)",
  model: "oklch(0.62 0.20 300)",
};

const TYPE_BG: Record<string, string> = {
  json: "oklch(0.52 0.22 260 / 0.08)",
  plot: "oklch(0.72 0.18 160 / 0.08)",
  model: "oklch(0.62 0.20 300 / 0.08)",
};

const SAMPLE_JSON = {
  top_k: 5,
  candidates: [
    {
      rank: 1,
      reactant_1: "PhB(OH)₂",
      catalyst: "Pd(OAc)₂",
      ligand: "SPhos",
      solvent: "THF/H₂O",
      predicted_yield: 94.2,
      uncertainty: 2.1,
    },
    {
      rank: 2,
      reactant_1: "4-MeOPhB(OH)₂",
      catalyst: "Pd₂(dba)₃",
      ligand: "XPhos",
      solvent: "DMF",
      predicted_yield: 91.5,
      uncertainty: 3.4,
    },
  ],
  model_version: "surrogate_suzuki_v3",
  generated_at: "2025-03-15T10:29:30Z",
};

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

export default function Artifacts() {
  const [filter, setFilter] = useState<ArtifactType>("all");
  const [search, setSearch] = useState("");
  const [previewId, setPreviewId] = useState<string | null>(null);

  const filtered = mockArtifacts.filter((a) => {
    const matchType = filter === "all" || a.type === filter;
    const matchSearch = a.name.toLowerCase().includes(search.toLowerCase()) || a.path.toLowerCase().includes(search.toLowerCase());
    return matchType && matchSearch;
  });

  const previewArtifact = mockArtifacts.find((a) => a.id === previewId);

  const counts = {
    all: mockArtifacts.length,
    json: mockArtifacts.filter((a) => a.type === "json").length,
    plot: mockArtifacts.filter((a) => a.type === "plot").length,
    model: mockArtifacts.filter((a) => a.type === "model").length,
  };

  return (
    <AppLayout
      title="Artifacts & Outputs"
      subtitle="Browse saved recommendations, reasoning outputs, models, and plots"
    >
      <div className="flex h-full" style={{ height: "calc(100vh - 73px)" }}>
        {/* Left: file browser */}
        <div className="flex-1 flex flex-col p-6 space-y-4 overflow-hidden">
          {/* Filters + search */}
          <div className="flex items-center gap-3">
            <div className="relative flex-1 max-w-xs">
              <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <input
                className="w-full pl-8 pr-3 py-2 text-sm border border-border rounded-lg bg-background focus:outline-none focus:ring-2 focus:ring-blue-500/30"
                placeholder="Search artifacts…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                style={{ fontFamily: "'Inter', sans-serif" }}
              />
            </div>
            <div className="flex gap-1.5">
              {(["all", "json", "plot", "model"] as ArtifactType[]).map((t) => (
                <button
                  key={t}
                  onClick={() => setFilter(t)}
                  className={cn(
                    "px-3 py-1.5 rounded-lg text-xs font-medium transition-colors capitalize",
                    filter === t
                      ? "bg-blue-600 text-white"
                      : "bg-muted text-muted-foreground hover:bg-muted/80"
                  )}
                >
                  {t} ({counts[t]})
                </button>
              ))}
            </div>
          </div>

          {/* File grid */}
          <ScrollArea className="flex-1">
            <div className="grid grid-cols-3 gap-3">
              {filtered.map((artifact) => {
                const Icon = TYPE_ICONS[artifact.type] || File;
                const color = TYPE_COLORS[artifact.type] || "oklch(0.52 0.015 250)";
                const bg = TYPE_BG[artifact.type] || "oklch(0.94 0.005 240)";
                return (
                  <div
                    key={artifact.id}
                    className={cn(
                      "labpilot-card p-4 cursor-pointer hover:shadow-md transition-all duration-150 group",
                      previewId === artifact.id && "ring-2 ring-blue-500/40"
                    )}
                    onClick={() => setPreviewId(artifact.id === previewId ? null : artifact.id)}
                  >
                    <div className="flex items-start gap-3">
                      <div
                        className="w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0"
                        style={{ background: bg }}
                      >
                        <Icon className="w-4.5 h-4.5" style={{ color }} />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="text-sm font-medium text-foreground truncate" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
                          {artifact.name}
                        </div>
                        <div className="text-xs text-muted-foreground truncate mt-0.5">
                          {artifact.path}
                        </div>
                        <div className="flex items-center gap-2 mt-2">
                          <span
                            className="text-xs px-1.5 py-0.5 rounded font-medium capitalize"
                            style={{ color, background: bg, fontFamily: "'Inter', sans-serif" }}
                          >
                            {artifact.type}
                          </span>
                          <span className="text-xs text-muted-foreground" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
                            {artifact.size}
                          </span>
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center justify-between mt-3 pt-3 border-t border-border">
                      <span className="text-xs text-muted-foreground" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
                        {formatDate(artifact.createdAt)}
                      </span>
                      <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                        <button
                          className="p-1 rounded hover:bg-muted transition-colors"
                          onClick={(e) => { e.stopPropagation(); setPreviewId(artifact.id); }}
                          title="Preview"
                        >
                          <Eye className="w-3.5 h-3.5 text-muted-foreground" />
                        </button>
                        <button
                          className="p-1 rounded hover:bg-muted transition-colors"
                          onClick={(e) => { e.stopPropagation(); toast.info("Download requires backend connection."); }}
                          title="Download"
                        >
                          <Download className="w-3.5 h-3.5 text-muted-foreground" />
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </ScrollArea>
        </div>

        {/* Right: Preview panel */}
        {previewId && previewArtifact && (
          <div
            className="w-96 flex-shrink-0 border-l border-border flex flex-col"
            style={{ background: "oklch(0.99 0.002 240)" }}
          >
            <div className="px-4 py-3 border-b border-border flex items-center justify-between">
              <div>
                <div className="text-sm font-semibold text-foreground" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
                  Preview
                </div>
                <div className="text-xs text-muted-foreground mt-0.5" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
                  {previewArtifact.name}
                </div>
              </div>
              <button onClick={() => setPreviewId(null)} className="text-muted-foreground hover:text-foreground">
                <X className="w-4 h-4" />
              </button>
            </div>

            <ScrollArea className="flex-1 p-4">
              {previewArtifact.type === "json" && (
                <div>
                  <div className="text-xs font-semibold text-muted-foreground mb-2 uppercase tracking-wide">
                    JSON Content
                  </div>
                  <pre
                    className="text-xs p-4 rounded-lg border border-border overflow-auto"
                    style={{
                      background: "oklch(0.175 0.04 255)",
                      color: "oklch(0.75 0.03 240)",
                      fontFamily: "'JetBrains Mono', monospace",
                      lineHeight: "1.6",
                    }}
                  >
                    {JSON.stringify(SAMPLE_JSON, null, 2)}
                  </pre>
                </div>
              )}
              {previewArtifact.type === "plot" && (
                <div>
                  <div className="text-xs font-semibold text-muted-foreground mb-2 uppercase tracking-wide">
                    Plot Preview
                  </div>
                  <div
                    className="rounded-lg border border-border flex items-center justify-center h-48"
                    style={{ background: "oklch(0.94 0.005 240)" }}
                  >
                    <div className="text-center">
                      <ImageIcon className="w-10 h-10 text-muted-foreground/40 mx-auto mb-2" />
                      <div className="text-xs text-muted-foreground">
                        {previewArtifact.name}
                      </div>
                      <div className="text-xs text-muted-foreground mt-0.5">
                        Connect to backend to load plot
                      </div>
                    </div>
                  </div>
                </div>
              )}
              {previewArtifact.type === "model" && (
                <div>
                  <div className="text-xs font-semibold text-muted-foreground mb-2 uppercase tracking-wide">
                    Model Info
                  </div>
                  <div
                    className="rounded-lg border border-border p-4"
                    style={{ background: "oklch(0.175 0.04 255)" }}
                  >
                    {[
                      ["File", previewArtifact.name],
                      ["Path", previewArtifact.path],
                      ["Size", previewArtifact.size],
                      ["Created", formatDate(previewArtifact.createdAt)],
                      ["Type", "scikit-learn RandomForest"],
                      ["Format", ".joblib"],
                    ].map(([k, v]) => (
                      <div key={String(k)} className="flex justify-between py-1.5 border-b last:border-0" style={{ borderColor: "oklch(0.28 0.04 255)" }}>
                        <span className="text-xs" style={{ color: "oklch(0.55 0.04 255)", fontFamily: "'Inter', sans-serif" }}>{k}</span>
                        <span className="text-xs" style={{ color: "oklch(0.75 0.03 240)", fontFamily: "'JetBrains Mono', monospace" }}>{String(v)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Metadata */}
              <div className="mt-4 space-y-2">
                <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                  File Details
                </div>
                {[
                  ["Path", previewArtifact.path],
                  ["Size", previewArtifact.size],
                  ["Created", formatDate(previewArtifact.createdAt)],
                ].map(([k, v]) => (
                  <div key={String(k)} className="flex justify-between text-xs">
                    <span className="text-muted-foreground">{k}</span>
                    <span className="text-foreground font-medium" style={{ fontFamily: "'JetBrains Mono', monospace" }}>{String(v)}</span>
                  </div>
                ))}
              </div>

              <Button
                size="sm"
                variant="outline"
                className="w-full mt-4 gap-2"
                onClick={() => toast.info("Download requires backend connection.")}
              >
                <Download className="w-3.5 h-3.5" />
                Download File
              </Button>
            </ScrollArea>
          </div>
        )}
      </div>
    </AppLayout>
  );
}
