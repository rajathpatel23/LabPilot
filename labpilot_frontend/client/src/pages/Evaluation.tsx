import { useEffect, useMemo, useState } from "react";
import AppLayout from "@/components/AppLayout";
import { apiGet, apiPost } from "@/lib/api";
import { BarChart, Bar, Cell, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { TrendingUp, Target, Zap, BarChart2 } from "lucide-react";

const STRATEGY_COLORS: Record<string, string> = {
  contextual_linucb: "#2563eb",
  adaptive: "#7c3aed",
  greedy: "#d97706",
  random: "#6b7280",
};

const CustomTooltip = ({ active, payload, label }: any) => {
  if (active && payload && payload.length) {
    return (
      <div className="rounded-lg border border-border shadow-lg p-3" style={{ background: "white", fontFamily: "'JetBrains Mono', monospace" }}>
        <div className="text-xs text-muted-foreground mb-1">{label}</div>
        {payload.map((p: any) => (
          <div key={p.dataKey} className="text-xs font-medium" style={{ color: p.fill || p.stroke || "#333" }}>
            {p.name}: {typeof p.value === "number" ? p.value.toFixed(1) : p.value}
          </div>
        ))}
      </div>
    );
  }
  return null;
};

type StrategyAgg = {
  name: string;
  runs: number;
  bestYield: number;
  avgBestYield: number;
  avgSteps: number;
  thresholdHitRate: number;
};

type EvalSnapshot = {
  methodology?: { policy?: string; notes?: string[] };
  sources?: { generalization_artifact?: string | null; ranking_artifact?: string | null };
  generalization?: {
    config?: Record<string, unknown>;
    strategies?: Array<{
      name: string;
      n_runs?: number;
      best_yield_mean?: number;
      best_yield_std?: number;
      trajectory_auc_mean?: number;
      trajectory_auc_std?: number;
      threshold_hit_rate?: number;
      avg_step_to_threshold_when_hit?: number;
      best_uplift_vs_random_mean?: number;
      auc_uplift_vs_random_mean?: number;
      win_rate_vs_random?: number;
    }>;
  };
  label_ranking?: {
    delta_vs_random?: {
      top1_delta?: number;
      top3_delta?: number;
      top5_delta?: number;
      mrr_delta?: number;
    };
  };
};

type ComparisonSuite = {
  selection_for_next_query?: {
    model_path?: string;
    strategy?: string;
    selection_policy?: string;
  };
  config?: {
    dataset_path?: string;
    model_path?: string;
    strategies?: string[];
    seeds?: number[];
  };
  artifact_path?: string;
};

export default function Evaluation() {
  const [snapshot, setSnapshot] = useState<EvalSnapshot | null>(null);
  const [suite, setSuite] = useState<ComparisonSuite | null>(null);
  const [runningSuite, setRunningSuite] = useState(false);
  const [suiteError, setSuiteError] = useState<string | null>(null);

  useEffect(() => {
    apiGet<EvalSnapshot>("/api/evaluation/snapshot")
      .then(setSnapshot)
      .catch(() => setSnapshot(null));
    apiGet<ComparisonSuite>("/api/evaluation/compare-suite/latest")
      .then(setSuite)
      .catch(() => setSuite(null));
  }, []);

  async function runAllComparisons() {
    setRunningSuite(true);
    setSuiteError(null);
    try {
      const datasetPath = String(snapshot?.generalization?.config?.data ?? "");
      if (!datasetPath) {
        throw new Error("No dataset path found in evaluation snapshot config.");
      }
      const payload = await apiPost<ComparisonSuite>("/api/evaluation/compare-suite", {
        dataset_path: datasetPath,
        model_path: null,
        strategies: ["random", "greedy", "adaptive", "contextual_linucb"],
        seeds: [11, 22, 33],
        budget: 20,
        n_init: 3,
        reward_mode: "improvement",
      });
      setSuite(payload);
    } catch (e) {
      setSuiteError(e instanceof Error ? e.message : "Failed to run comparison suite.");
    } finally {
      setRunningSuite(false);
    }
  }

  const strategies = useMemo<StrategyAgg[]>(() => {
    const arr = snapshot?.generalization?.strategies ?? [];
    return arr.map((s) => {
      return {
        name: s.name,
        runs: Number(s.n_runs ?? 0),
        bestYield: Number(s.best_yield_mean ?? 0),
        avgBestYield: Number(s.best_yield_mean ?? 0),
        avgSteps: Number(s.avg_step_to_threshold_when_hit ?? 0),
        thresholdHitRate: Number(s.threshold_hit_rate ?? 0),
      };
    });
  }, [snapshot]);

  const hitRateData = strategies.map((s) => ({ ...s, hitRatePct: s.thresholdHitRate * 100 }));
  const bestStrategy = [...strategies].sort((a, b) => b.avgBestYield - a.avgBestYield)[0];
  const fastestStrategy = [...strategies].sort((a, b) => a.avgSteps - b.avgSteps)[0];
  const bestHit = [...strategies].sort((a, b) => b.thresholdHitRate - a.thresholdHitRate)[0];
  const avgAucProxy = strategies.length ? strategies.reduce((acc, s) => acc + s.avgBestYield, 0) / strategies.length : 0;
  const rankingDelta = snapshot?.label_ranking?.delta_vs_random;

  return (
    <AppLayout
      title="Evaluation Dashboard"
      subtitle="Benchmark comparison across all experiment strategies"
    >
      <div className="p-8 space-y-6">
        {/* Top metric cards */}
        <div className="grid grid-cols-4 gap-4">
          {[
            {
              label: "Best Yield (LinUCB)",
              value: bestStrategy ? `${bestStrategy.avgBestYield.toFixed(1)}%` : "—",
              sub: bestStrategy ? bestStrategy.name : "n/a",
              icon: TrendingUp,
              color: "oklch(0.52 0.22 260)",
              bg: "oklch(0.52 0.22 260 / 0.08)",
            },
            {
              label: "Avg Trajectory AUC",
              value: avgAucProxy.toFixed(1),
              sub: `across ${strategies.length} strategies`,
              icon: BarChart2,
              color: "oklch(0.72 0.18 160)",
              bg: "oklch(0.72 0.18 160 / 0.08)",
            },
            {
              label: "Best Hit Rate",
              value: bestHit ? `${(bestHit.thresholdHitRate * 100).toFixed(0)}%` : "—",
              sub: bestHit ? bestHit.name : "n/a",
              icon: Target,
              color: "oklch(0.75 0.18 80)",
              bg: "oklch(0.75 0.18 80 / 0.08)",
            },
            {
              label: "Fastest to Threshold",
              value: fastestStrategy ? `${fastestStrategy.avgSteps.toFixed(1)} steps` : "—",
              sub: fastestStrategy ? fastestStrategy.name : "n/a",
              icon: Zap,
              color: "oklch(0.62 0.20 300)",
              bg: "oklch(0.62 0.20 300 / 0.08)",
            },
          ].map(({ label, value, sub, icon: Icon, color, bg }) => (
            <div key={label} className="labpilot-card p-5">
              <div className="flex items-center gap-2 mb-3">
                <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: bg }}>
                  <Icon className="w-4 h-4" style={{ color }} />
                </div>
                <span className="text-xs text-muted-foreground font-medium">{label}</span>
              </div>
              <div className="text-2xl font-medium tabular-nums" style={{ fontFamily: "'JetBrains Mono', monospace", color }}>
                {value}
              </div>
              <div className="text-xs text-muted-foreground mt-1">{sub}</div>
            </div>
          ))}
        </div>

        {/* Charts row 1 */}
        <div className="grid grid-cols-3 gap-6">
          {/* Best yield bar chart */}
          <div className="labpilot-card p-5">
            <h3 className="font-semibold text-foreground text-sm mb-4" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
              Best Yield by Strategy
            </h3>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={strategies} margin={{ top: 5, right: 10, left: 0, bottom: 20 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis
                  dataKey="name"
                  tick={{ fontSize: 9, fontFamily: "'JetBrains Mono', monospace" }}
                  tickFormatter={(v) => v.replace("contextual_", "")}
                  angle={-20}
                  textAnchor="end"
                />
                <YAxis domain={[60, 100]} tick={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace" }} tickFormatter={(v) => `${v}%`} />
                <Tooltip content={<CustomTooltip />} />
                <Bar dataKey="avgBestYield" name="Avg Best Yield" radius={[4, 4, 0, 0]}>
                  {strategies.map((s) => (
                    <Cell key={s.name} fill={STRATEGY_COLORS[s.name]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Threshold hit rate */}
          <div className="labpilot-card p-5">
            <h3 className="font-semibold text-foreground text-sm mb-4" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
              Threshold Hit Rate
            </h3>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={hitRateData} margin={{ top: 5, right: 10, left: 0, bottom: 20 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis
                  dataKey="name"
                  tick={{ fontSize: 9, fontFamily: "'JetBrains Mono', monospace" }}
                  tickFormatter={(v) => v.replace("contextual_", "")}
                  angle={-20}
                  textAnchor="end"
                />
                <YAxis domain={[0, 100]} tick={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace" }} tickFormatter={(v) => `${v}%`} />
                <Tooltip content={<CustomTooltip />} />
                <Bar dataKey="hitRatePct" name="Hit Rate %" radius={[4, 4, 0, 0]}>
                  {hitRateData.map((s) => (
                    <Cell key={s.name} fill={STRATEGY_COLORS[s.name]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Step to threshold */}
          <div className="labpilot-card p-5">
            <h3 className="font-semibold text-foreground text-sm mb-4" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
              Avg Steps to Threshold
            </h3>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={strategies} layout="vertical" margin={{ top: 5, right: 20, left: 60, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis type="number" domain={[0, 20]} tick={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace" }} />
                <YAxis
                  type="category"
                  dataKey="name"
                  tick={{ fontSize: 9, fontFamily: "'JetBrains Mono', monospace" }}
                  tickFormatter={(v) => v.replace("contextual_", "")}
                  width={55}
                />
                <Tooltip content={<CustomTooltip />} />
                <Bar dataKey="avgSteps" name="Avg Steps" radius={[0, 4, 4, 0]}>
                  {strategies.map((s) => (
                    <Cell key={s.name} fill={STRATEGY_COLORS[s.name]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="labpilot-card p-5">
          <h3 className="font-semibold text-foreground text-sm mb-2" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
            Fairness Protocol
          </h3>
          <p className="text-sm text-muted-foreground mb-2">
            {snapshot?.methodology?.policy
              ? `Policy: ${snapshot.methodology.policy}`
              : "Policy: holdout-first"}
          </p>
          <ul className="text-xs text-muted-foreground list-disc pl-5 space-y-1">
            {(snapshot?.methodology?.notes ?? []).map((n, i) => (
              <li key={i}>{n}</li>
            ))}
          </ul>
          <div className="mt-3 text-[11px] text-muted-foreground">
            Source (generalization): {snapshot?.sources?.generalization_artifact ?? "n/a"}
          </div>
          <div className="text-[11px] text-muted-foreground">
            Source (label ranking): {snapshot?.sources?.ranking_artifact ?? "n/a"}
          </div>
        </div>

        <div className="labpilot-card p-5">
          <div className="flex items-center justify-between gap-4">
            <div>
              <h3 className="font-semibold text-foreground text-sm mb-1" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
                Compare All Runs and Auto-Select for Next Query
              </h3>
              <p className="text-xs text-muted-foreground">
                Runs all strategies across fixed seeds, then picks the strategy with highest mean best yield.
              </p>
            </div>
            <button
              onClick={runAllComparisons}
              disabled={runningSuite}
              className="px-3 py-2 rounded-md border border-border text-sm hover:bg-muted disabled:opacity-60"
            >
              {runningSuite ? "Running..." : "Run Comparison Suite"}
            </button>
          </div>
          {suiteError ? <div className="mt-3 text-xs text-red-600">{suiteError}</div> : null}
          <div className="mt-3 grid grid-cols-3 gap-3">
            <div className="rounded-lg border border-border p-3">
              <div className="text-xs text-muted-foreground">Selected Strategy</div>
              <div className="text-sm font-semibold">{suite?.selection_for_next_query?.strategy ?? "n/a"}</div>
            </div>
            <div className="rounded-lg border border-border p-3">
              <div className="text-xs text-muted-foreground">Selected Model Path</div>
              <div className="text-xs font-mono break-all">{suite?.selection_for_next_query?.model_path ?? "n/a"}</div>
            </div>
            <div className="rounded-lg border border-border p-3">
              <div className="text-xs text-muted-foreground">Selection Policy</div>
              <div className="text-sm">{suite?.selection_for_next_query?.selection_policy ?? "n/a"}</div>
            </div>
          </div>
          <div className="mt-2 text-[11px] text-muted-foreground">
            Comparison artifact: {suite?.artifact_path ?? "n/a"}
          </div>
        </div>

        <div className="labpilot-card p-5">
          <h3 className="font-semibold text-foreground text-sm mb-2" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
            Label Ranking Delta vs Random
          </h3>
          <div className="grid grid-cols-4 gap-3">
            {[
              ["Top-1 Δ", rankingDelta?.top1_delta ?? 0],
              ["Top-3 Δ", rankingDelta?.top3_delta ?? 0],
              ["Top-5 Δ", rankingDelta?.top5_delta ?? 0],
              ["MRR Δ", rankingDelta?.mrr_delta ?? 0],
            ].map(([k, v]) => (
              <div key={String(k)} className="rounded-lg border border-border p-3">
                <div className="text-xs text-muted-foreground">{k}</div>
                <div className="text-lg font-mono">{(Number(v) * 100).toFixed(2)}%</div>
              </div>
            ))}
          </div>
        </div>

        {/* Summary table */}
        <div className="labpilot-card overflow-hidden">
          <div className="px-5 py-4 border-b border-border">
            <h3 className="font-semibold text-foreground text-sm" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
              Benchmark Summary
            </h3>
          </div>
          <table className="w-full">
            <thead>
              <tr className="border-b border-border">
                {["Strategy", "Runs", "Avg Best Yield", "Hit Rate (>=85%)", "Avg Steps", "Rank"].map((h) => (
                  <th key={h} className="px-5 py-2.5 text-left text-xs font-medium text-muted-foreground">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {strategies.map((s, i) => (
                <tr key={s.name} className="border-b border-border last:border-0 hover:bg-muted/30 transition-colors">
                  <td className="px-5 py-3.5">
                    <div className="flex items-center gap-2">
                      <span
                        className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                        style={{ background: STRATEGY_COLORS[s.name] }}
                      />
                      <span className="text-sm font-medium text-foreground" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
                        {s.name}
                      </span>
                    </div>
                  </td>
                  <td className="px-5 py-3.5">
                    <span className="text-sm font-semibold tabular-nums" style={{ fontFamily: "'JetBrains Mono', monospace", color: STRATEGY_COLORS[s.name] ?? "#6b7280" }}>
                      {s.runs}
                    </span>
                  </td>
                  <td className="px-5 py-3.5">
                    <span className="text-sm tabular-nums text-foreground" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
                      {s.avgBestYield.toFixed(2)}%
                    </span>
                  </td>
                  <td className="px-5 py-3.5">
                    <div className="flex items-center gap-2">
                      <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden max-w-[80px]">
                        <div
                          className="h-full rounded-full"
                            style={{ width: `${s.thresholdHitRate * 100}%`, background: STRATEGY_COLORS[s.name] ?? "#6b7280" }}
                        />
                      </div>
                      <span className="text-sm tabular-nums text-foreground" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
                        {(s.thresholdHitRate * 100).toFixed(0)}%
                      </span>
                    </div>
                  </td>
                  <td className="px-5 py-3.5">
                    <span className="text-sm tabular-nums text-foreground" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
                      {s.avgSteps.toFixed(2)}
                    </span>
                  </td>
                  <td className="px-5 py-3.5">
                    <span
                      className="inline-flex items-center justify-center w-6 h-6 rounded-full text-xs font-bold text-white"
                      style={{ background: STRATEGY_COLORS[s.name] }}
                    >
                      {i + 1}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </AppLayout>
  );
}
