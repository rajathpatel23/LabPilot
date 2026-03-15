// LabPilot Experiment Simulation
// Design: Clinical Research Portal
// Form + runs table + detail view with Recharts (best-so-far + observed yield)

import { useEffect, useMemo, useState } from "react";
import AppLayout from "@/components/AppLayout";
import { apiGet, apiPost, type ApiExperimentRun } from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  Beaker,
  Plus,
  ChevronLeft,
  TrendingUp,
  X,
  Loader2,
} from "lucide-react";
import { toast } from "sonner";

const EXP_BG = "https://d2xsxph8kpxj0f.cloudfront.net/310519663435888256/LwQaGTexsoKSwC82giZxAm/labpilot-experiment-bg-P5fq7pAhbxawME5iMPyC55.webp";

const STRATEGY_COLORS: Record<string, string> = {
  contextual_linucb: "#2563eb",
  adaptive: "#7c3aed",
  greedy: "#d97706",
  random: "#6b7280",
};

const STRATEGIES = ["contextual_linucb", "greedy", "adaptive", "random", "bandit_ucb"];

function StrategyBadge({ strategy }: { strategy: string }) {
  const color = STRATEGY_COLORS[strategy] || "#6b7280";
  return (
    <span
      className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border"
      style={{
        color,
        borderColor: `${color}40`,
        background: `${color}10`,
        fontFamily: "'JetBrains Mono', monospace",
      }}
    >
      {strategy}
    </span>
  );
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export default function Experiments() {
  const [showForm, setShowForm] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [runs, setRuns] = useState<ApiExperimentRun[]>([]);

  // Form state
  const [strategy, setStrategy] = useState("contextual_linucb");
  const [budget, setBudget] = useState("20");
  const [nInit, setNInit] = useState("3");
  const [seed, setSeed] = useState("42");
  const [beta, setBeta] = useState("0.8");
  const [linucbAlpha, setLinucbAlpha] = useState("1.0");

  const selectedRun = runs.find((r) => r.id === selectedId);
  const datasetPath = "data/Suzuki-Miyaura/aap9112_Data_File_S1.xlsx";
  const modelPath = "artifacts/surrogate_suzuki.joblib";

  async function loadRuns() {
    const data = await apiGet<ApiExperimentRun[]>("/api/experiments/runs");
    setRuns(data);
  }

  useEffect(() => {
    loadRuns().catch(() => toast.error("Failed to load experiment runs."));
  }, []);

  const strategyCounts = useMemo(() => {
    return runs.reduce<Record<string, number>>((acc, run) => {
      acc[run.strategy] = (acc[run.strategy] ?? 0) + 1;
      return acc;
    }, {});
  }, [runs]);

  const handleSubmit = async () => {
    setSubmitting(true);
    try {
      await apiPost("/api/experiments/runs", {
        strategy,
        dataset_path: datasetPath,
        model_path: modelPath,
        budget: Number(budget),
        n_init: Number(nInit),
        seed: Number(seed),
        reward_mode: "improvement",
        beta: Number(beta),
        linucb_alpha: Number(linucbAlpha),
        linucb_lambda: 1.0,
      });
      await loadRuns();
      setSubmitting(false);
      setShowForm(false);
      toast.success("Simulation submitted.");
    } catch (e) {
      setSubmitting(false);
      toast.error(`Failed to submit simulation: ${String(e)}`);
    }
  };

  if (selectedRun) {
    return (
      <AppLayout
        title={`Experiment: ${selectedRun.strategy}`}
        subtitle={`Run ID: ${selectedRun.id} · ${selectedRun.summary?.steps_completed ?? 0} steps · Budget: ${selectedRun.budget}`}
        actions={
          <Button variant="outline" size="sm" className="gap-2" onClick={() => setSelectedId(null)}>
            <ChevronLeft className="w-3.5 h-3.5" />
            Back to Runs
          </Button>
        }
      >
        <div className="p-8 space-y-6">
          {/* Summary cards */}
          <div className="grid grid-cols-4 gap-4">
            {[
              { label: "Best Yield", value: `${selectedRun.summary?.best_yield?.toFixed(2) ?? "—"}%`, icon: TrendingUp, color: "oklch(0.52 0.22 260)" },
              { label: "Steps Completed", value: `${selectedRun.summary?.steps_completed ?? 0}`, icon: TrendingUp, color: "oklch(0.72 0.18 160)" },
              { label: "Status", value: selectedRun.status, icon: TrendingUp, color: "oklch(0.75 0.18 80)" },
              { label: "Seed", value: String(selectedRun.seed), icon: TrendingUp, color: "oklch(0.62 0.20 300)" },
            ].map(({ label, value, icon: Icon, color }) => (
              <div key={label} className="labpilot-card p-5">
                <div className="flex items-center gap-2 mb-3">
                  <Icon className="w-4 h-4" style={{ color }} />
                  <span className="text-xs text-muted-foreground font-medium">{label}</span>
                </div>
                <div className="text-2xl font-medium tabular-nums" style={{ fontFamily: "'JetBrains Mono', monospace", color }}>
                  {value}
                </div>
                <div className="mt-2">
                  <StrategyBadge strategy={selectedRun.strategy} />
                </div>
              </div>
            ))}
          </div>

          <div className="labpilot-card p-5">
            <h3 className="font-semibold text-foreground text-sm mb-3" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
              Output Artifact
            </h3>
            <div className="text-xs text-muted-foreground mb-1">Full trajectory details are available in backend artifact JSON:</div>
            <code className="text-xs break-all" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
              {selectedRun.output_path ?? "No output path yet"}
            </code>
          </div>

          {/* Config details */}
          <div className="labpilot-card p-5">
            <h3 className="font-semibold text-foreground text-sm mb-4" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
              Run Configuration
            </h3>
            <div className="grid grid-cols-4 gap-4 text-sm">
              {[
                ["Strategy", selectedRun.strategy],
                ["Budget", selectedRun.budget],
                ["n_init", selectedRun.n_init],
                ["Seed", selectedRun.seed],
                ["Status", selectedRun.status],
                ["Dataset", selectedRun.dataset_path.split("/").pop()],
                ["Model", selectedRun.model_path.split("/").pop()],
                ["Created", formatDate(selectedRun.created_at)],
              ].map(([k, v]) => (
                <div key={String(k)}>
                  <div className="text-xs text-muted-foreground mb-0.5">{k}</div>
                  <div className="text-sm font-medium text-foreground" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
                    {String(v)}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </AppLayout>
    );
  }

  return (
    <AppLayout
      title="Experiment Simulation"
      subtitle="Run bandit strategy simulations and compare policies"
      actions={
        <Button size="sm" className="gap-2" onClick={() => setShowForm(!showForm)}>
          <Plus className="w-3.5 h-3.5" />
          New Simulation
        </Button>
      }
    >
      <div className="p-8 space-y-6">
        {/* Banner */}
        <div className="relative rounded-xl overflow-hidden h-32">
          <img src={EXP_BG} alt="" className="w-full h-full object-cover" />
          <div className="absolute inset-0" style={{ background: "linear-gradient(to right, oklch(0.175 0.04 255 / 0.9) 0%, oklch(0.175 0.04 255 / 0.5) 60%, transparent 100%)" }} />
          <div className="absolute inset-0 flex items-center px-8">
            <div>
              <div className="text-xs font-medium tracking-widest mb-1" style={{ color: "oklch(0.75 0.18 80)", fontFamily: "'Inter', sans-serif" }}>
                BANDIT OPTIMIZATION
              </div>
              <div className="text-xl font-bold text-white" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
                Strategy Comparison
              </div>
              <div className="text-sm mt-0.5" style={{ color: "oklch(0.75 0.03 240)" }}>
                LinUCB · Adaptive · Greedy · Random — 4 strategies evaluated
              </div>
            </div>
          </div>
        </div>

        {/* New Simulation Form */}
        {showForm && (
          <div className="labpilot-card p-6">
            <div className="flex items-center justify-between mb-5">
              <h3 className="font-semibold text-foreground" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
                New Simulation Run
              </h3>
              <button onClick={() => setShowForm(false)} className="text-muted-foreground hover:text-foreground">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="grid grid-cols-3 gap-4 mb-4">
              <div>
                <label className="text-xs font-medium text-muted-foreground mb-1.5 block">Strategy *</label>
                <select
                  className="w-full text-sm border border-border rounded-lg px-3 py-2 bg-background focus:outline-none focus:ring-2 focus:ring-blue-500/30"
                  value={strategy}
                  onChange={(e) => setStrategy(e.target.value)}
                  style={{ fontFamily: "'JetBrains Mono', monospace" }}
                >
                  {STRATEGIES.map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-xs font-medium text-muted-foreground mb-1.5 block">Budget (steps)</label>
                <input
                  type="number"
                  className="w-full text-sm border border-border rounded-lg px-3 py-2 bg-background focus:outline-none focus:ring-2 focus:ring-blue-500/30"
                  style={{ fontFamily: "'JetBrains Mono', monospace" }}
                  value={budget}
                  onChange={(e) => setBudget(e.target.value)}
                />
              </div>
              <div>
                <label className="text-xs font-medium text-muted-foreground mb-1.5 block">n_init</label>
                <input
                  type="number"
                  className="w-full text-sm border border-border rounded-lg px-3 py-2 bg-background focus:outline-none focus:ring-2 focus:ring-blue-500/30"
                  style={{ fontFamily: "'JetBrains Mono', monospace" }}
                  value={nInit}
                  onChange={(e) => setNInit(e.target.value)}
                />
              </div>
              <div>
                <label className="text-xs font-medium text-muted-foreground mb-1.5 block">Seed</label>
                <input
                  type="number"
                  className="w-full text-sm border border-border rounded-lg px-3 py-2 bg-background focus:outline-none focus:ring-2 focus:ring-blue-500/30"
                  style={{ fontFamily: "'JetBrains Mono', monospace" }}
                  value={seed}
                  onChange={(e) => setSeed(e.target.value)}
                />
              </div>
              <div>
                <label className="text-xs font-medium text-muted-foreground mb-1.5 block">Beta</label>
                <input
                  type="number"
                  step="0.1"
                  className="w-full text-sm border border-border rounded-lg px-3 py-2 bg-background focus:outline-none focus:ring-2 focus:ring-blue-500/30"
                  style={{ fontFamily: "'JetBrains Mono', monospace" }}
                  value={beta}
                  onChange={(e) => setBeta(e.target.value)}
                />
              </div>
              <div>
                <label className="text-xs font-medium text-muted-foreground mb-1.5 block">LinUCB Alpha</label>
                <input
                  type="number"
                  step="0.1"
                  className="w-full text-sm border border-border rounded-lg px-3 py-2 bg-background focus:outline-none focus:ring-2 focus:ring-blue-500/30"
                  style={{ fontFamily: "'JetBrains Mono', monospace" }}
                  value={linucbAlpha}
                  onChange={(e) => setLinucbAlpha(e.target.value)}
                />
              </div>
            </div>
            <div className="flex justify-end gap-3">
              <Button variant="outline" size="sm" onClick={() => setShowForm(false)}>Cancel</Button>
              <Button size="sm" onClick={handleSubmit} disabled={submitting} className="gap-2">
                {submitting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Beaker className="w-3.5 h-3.5" />}
                Launch Simulation
              </Button>
            </div>
          </div>
        )}

        {/* Strategy snapshot */}
        <div className="labpilot-card p-5">
          <h3 className="font-semibold text-foreground text-sm mb-4" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
            Strategy Snapshot
          </h3>
          <div className="grid grid-cols-5 gap-3">
            {Object.entries(strategyCounts).map(([name, count]) => (
              <div key={name} className="rounded-lg border border-border p-3">
                <div className="mb-1">
                  <StrategyBadge strategy={name} />
                </div>
                <div className="text-xs text-muted-foreground">{count} runs</div>
              </div>
            ))}
          </div>
        </div>

        {/* Runs Table */}
        <div className="labpilot-card overflow-hidden">
          <div className="px-5 py-4 border-b border-border">
            <h3 className="font-semibold text-foreground text-sm" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
              Simulation Runs
            </h3>
          </div>
          <div>
            <div className="grid grid-cols-12 px-5 py-2.5 text-xs font-medium text-muted-foreground border-b border-border">
              <div className="col-span-3">Strategy</div>
              <div className="col-span-1 text-right">Budget</div>
              <div className="col-span-2 text-right">Best Yield</div>
              <div className="col-span-2 text-right">Traj. AUC</div>
              <div className="col-span-2 text-right">Hit Rate</div>
              <div className="col-span-2 text-right">Created</div>
            </div>
            {runs.map((run) => (
              <button
                key={run.id}
                className="grid grid-cols-12 w-full px-5 py-3.5 hover:bg-muted/40 transition-colors text-left border-b border-border last:border-0"
                onClick={() => setSelectedId(run.id)}
              >
                <div className="col-span-3 flex items-center">
                  <StrategyBadge strategy={run.strategy} />
                </div>
                <div className="col-span-1 flex items-center justify-end">
                  <span className="text-sm tabular-nums text-muted-foreground" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
                    {run.budget}
                  </span>
                </div>
                <div className="col-span-2 flex items-center justify-end">
                  <span className="text-sm font-semibold tabular-nums" style={{ fontFamily: "'JetBrains Mono', monospace", color: STRATEGY_COLORS[run.strategy] }}>
                    {run.summary?.best_yield?.toFixed(2) ?? "—"}%
                  </span>
                </div>
                <div className="col-span-2 flex items-center justify-end">
                  <span className="text-sm tabular-nums text-muted-foreground" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
                    —
                  </span>
                </div>
                <div className="col-span-2 flex items-center justify-end">
                  <span className="text-sm tabular-nums text-muted-foreground" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
                    —
                  </span>
                </div>
                <div className="col-span-2 flex items-center justify-end">
                  <span className="text-xs text-muted-foreground" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
                    {formatDate(run.created_at)}
                  </span>
                </div>
              </button>
            ))}
          </div>
        </div>
      </div>
    </AppLayout>
  );
}
