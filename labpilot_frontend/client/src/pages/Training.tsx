// LabPilot Model Training
// Design: Clinical Research Portal
// Training form + runs table + expandable detail card

import { useEffect, useState } from "react";
import AppLayout from "@/components/AppLayout";
import { apiGet, apiPost, type ApiTrainingRun } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  BrainCircuit,
  Plus,
  ChevronDown,
  ChevronRight,
  CheckCircle2,
  Loader2,
  XCircle,
  Clock,
  Database,
  Target,
  Layers,
  BarChart2,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import { useLocation } from "wouter";

const TRAINING_BG = "https://d2xsxph8kpxj0f.cloudfront.net/310519663435888256/LwQaGTexsoKSwC82giZxAm/labpilot-training-bg-iNGnUHkY6eN8wmyinCQSKw.webp";

const DEFAULT_FEATURES = [
  "Reactant_1_Short_Hand",
  "Reactant_1_eq",
  "Reactant_1_mmol",
  "Reactant_2_Name",
  "Reactant_2_eq",
  "Catalyst_1_Short_Hand",
  "Catalyst_1_eq",
  "Ligand_Short_Hand",
  "Ligand_eq",
  "Reagent_1_Short_Hand",
  "Reagent_1_eq",
  "Solvent_1_Short_Hand",
];

function StatusBadge({ status }: { status: string }) {
  if (status === "running")
    return (
      <span className="status-badge-running">
        <Loader2 className="w-3 h-3 animate-spin" /> Running
      </span>
    );
  if (status === "completed")
    return (
      <span className="status-badge-completed">
        <CheckCircle2 className="w-3 h-3" /> Completed
      </span>
    );
  if (status === "failed")
    return (
      <span className="status-badge-failed">
        <XCircle className="w-3 h-3" /> Failed
      </span>
    );
  return (
    <span className="status-badge-pending">
      <Clock className="w-3 h-3" /> Pending
    </span>
  );
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export default function Training() {
  const [location] = useLocation();
  const [showForm, setShowForm] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [runs, setRuns] = useState<ApiTrainingRun[]>([]);

  // Form state
  const [dataset, setDataset] = useState("data/Suzuki-Miyaura/aap9112_Data_File_S1.xlsx");
  const [target, setTarget] = useState("Product_Yield_PCT_Area_UV");
  const [outputName, setOutputName] = useState("surrogate_suzuki_v4");
  const [features, setFeatures] = useState<string[]>(DEFAULT_FEATURES);
  const [newFeature, setNewFeature] = useState("");

  useEffect(() => {
    const idx = location.indexOf("?");
    if (idx < 0) return;
    const qs = location.slice(idx + 1);
    const params = new URLSearchParams(qs);
    const datasetParam = params.get("dataset");
    if (datasetParam) {
      setDataset(datasetParam);
      setShowForm(true);
      toast.success("Dataset path prefilled from upload. Configure target/features and start training.");
    }
  }, [location]);

  async function loadRuns() {
    const data = await apiGet<ApiTrainingRun[]>("/api/training/runs");
    setRuns(data);
    if (!expandedId && data.length > 0) {
      setExpandedId(data[0].id);
    }
  }

  useEffect(() => {
    loadRuns().catch(() => toast.error("Failed to load training runs."));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSubmit = async () => {
    if (!dataset || !target || !outputName) {
      toast.error("Please fill in all required fields.");
      return;
    }
    setSubmitting(true);
    try {
      await apiPost("/api/training/runs", {
        dataset_path: dataset,
        target_column: target,
        features,
        output_name: outputName,
      });
      await loadRuns();
      setSubmitting(false);
      setShowForm(false);
      toast.success("Training job submitted.");
    } catch (e) {
      setSubmitting(false);
      toast.error(`Failed to submit training job: ${String(e)}`);
    }
  };

  const removeFeature = (f: string) => setFeatures(features.filter((x) => x !== f));
  const addFeature = () => {
    if (newFeature.trim() && !features.includes(newFeature.trim())) {
      setFeatures([...features, newFeature.trim()]);
      setNewFeature("");
    }
  };

  return (
    <AppLayout
      title="Model Training"
      subtitle="Train surrogate models to predict reaction yields"
      actions={
        <Button size="sm" className="gap-2" onClick={() => setShowForm(!showForm)}>
          <Plus className="w-3.5 h-3.5" />
          New Training Run
        </Button>
      }
    >
      <div className="p-8 space-y-6">
        {/* Banner */}
        <div className="relative rounded-xl overflow-hidden h-32">
          <img src={TRAINING_BG} alt="" className="w-full h-full object-cover" />
          <div className="absolute inset-0" style={{ background: "linear-gradient(to right, oklch(0.175 0.04 255 / 0.9) 0%, oklch(0.175 0.04 255 / 0.5) 60%, transparent 100%)" }} />
          <div className="absolute inset-0 flex items-center px-8">
            <div>
              <div className="text-xs font-medium tracking-widest mb-1" style={{ color: "oklch(0.72 0.18 160)", fontFamily: "'Inter', sans-serif" }}>
                SURROGATE MODEL
              </div>
              <div className="text-xl font-bold text-white" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
                Random Forest Regressor
              </div>
              <div className="text-sm mt-0.5" style={{ color: "oklch(0.75 0.03 240)" }}>
                Best model: R²=0.912 · MAE=3.42 · 892 train / 224 test
              </div>
            </div>
          </div>
        </div>

        {/* New Training Form */}
        {showForm && (
          <div className="labpilot-card p-6">
            <div className="flex items-center justify-between mb-5">
              <h3 className="font-semibold text-foreground" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
                New Training Run
              </h3>
              <button onClick={() => setShowForm(false)} className="text-muted-foreground hover:text-foreground">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="grid grid-cols-3 gap-4 mb-4">
              <div>
                <label className="text-xs font-medium text-muted-foreground mb-1.5 block">Dataset Path *</label>
                <input
                  className="w-full text-sm border border-border rounded-lg px-3 py-2 bg-background focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-400"
                  style={{ fontFamily: "'JetBrains Mono', monospace" }}
                  value={dataset}
                  onChange={(e) => setDataset(e.target.value)}
                  placeholder="data/..."
                />
              </div>
              <div>
                <label className="text-xs font-medium text-muted-foreground mb-1.5 block">Target Column *</label>
                <input
                  className="w-full text-sm border border-border rounded-lg px-3 py-2 bg-background focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-400"
                  style={{ fontFamily: "'JetBrains Mono', monospace" }}
                  value={target}
                  onChange={(e) => setTarget(e.target.value)}
                  placeholder="column name"
                />
              </div>
              <div>
                <label className="text-xs font-medium text-muted-foreground mb-1.5 block">Output Name *</label>
                <input
                  className="w-full text-sm border border-border rounded-lg px-3 py-2 bg-background focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-400"
                  style={{ fontFamily: "'JetBrains Mono', monospace" }}
                  value={outputName}
                  onChange={(e) => setOutputName(e.target.value)}
                  placeholder="model name"
                />
              </div>
            </div>

            {/* Features */}
            <div className="mb-4">
              <label className="text-xs font-medium text-muted-foreground mb-2 block">Feature Columns</label>
              <div className="flex flex-wrap gap-1.5 p-3 rounded-lg border border-border bg-muted/30 min-h-[60px]">
                {features.map((f) => (
                  <span
                    key={f}
                    className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs bg-blue-50 text-blue-700 border border-blue-200"
                    style={{ fontFamily: "'JetBrains Mono', monospace" }}
                  >
                    {f}
                    <button onClick={() => removeFeature(f)} className="hover:text-blue-900 ml-0.5">
                      <X className="w-2.5 h-2.5" />
                    </button>
                  </span>
                ))}
              </div>
              <div className="flex gap-2 mt-2">
                <input
                  className="flex-1 text-xs border border-border rounded-lg px-3 py-1.5 bg-background focus:outline-none focus:ring-2 focus:ring-blue-500/30"
                  style={{ fontFamily: "'JetBrains Mono', monospace" }}
                  placeholder="Add feature column name…"
                  value={newFeature}
                  onChange={(e) => setNewFeature(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && addFeature()}
                />
                <Button size="sm" variant="outline" onClick={addFeature} className="text-xs">
                  Add
                </Button>
              </div>
            </div>

            <div className="flex justify-end gap-3">
              <Button variant="outline" size="sm" onClick={() => setShowForm(false)}>
                Cancel
              </Button>
              <Button size="sm" onClick={handleSubmit} disabled={submitting} className="gap-2">
                {submitting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <BrainCircuit className="w-3.5 h-3.5" />}
                Submit Training Job
              </Button>
            </div>
          </div>
        )}

        {/* Runs Table */}
        <div className="labpilot-card overflow-hidden">
          <div className="px-5 py-4 border-b border-border">
            <h3 className="font-semibold text-foreground text-sm" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
              Training Runs
            </h3>
          </div>
          <div>
            {/* Header */}
            <div
              className="grid grid-cols-12 px-5 py-2.5 text-xs font-medium text-muted-foreground border-b border-border"
              style={{ fontFamily: "'Inter', sans-serif" }}
            >
              <div className="col-span-1"></div>
              <div className="col-span-3">Model Name</div>
              <div className="col-span-2">Status</div>
              <div className="col-span-1 text-right">R²</div>
              <div className="col-span-1 text-right">MAE</div>
              <div className="col-span-1 text-right">Train</div>
              <div className="col-span-1 text-right">Test</div>
              <div className="col-span-2 text-right">Created</div>
            </div>

            {runs.map((run) => (
              <div key={run.id}>
                <button
                  className="grid grid-cols-12 w-full px-5 py-3.5 hover:bg-muted/40 transition-colors text-left border-b border-border last:border-0"
                  onClick={() => setExpandedId(expandedId === run.id ? null : run.id)}
                >
                  <div className="col-span-1 flex items-center">
                    {expandedId === run.id ? (
                      <ChevronDown className="w-3.5 h-3.5 text-muted-foreground" />
                    ) : (
                      <ChevronRight className="w-3.5 h-3.5 text-muted-foreground" />
                    )}
                  </div>
                  <div className="col-span-3 flex items-center">
                    <span className="text-sm font-medium text-foreground" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
                      {run.model_path?.split("/").pop() ?? run.id}
                    </span>
                  </div>
                  <div className="col-span-2 flex items-center">
                    <StatusBadge status={run.status} />
                  </div>
                  <div className="col-span-1 flex items-center justify-end">
                    <span className="text-sm tabular-nums" style={{ fontFamily: "'JetBrains Mono', monospace", color: typeof run.metrics?.r2 === "number" ? "oklch(0.52 0.22 260)" : "oklch(0.65 0.015 250)" }}>
                      {typeof run.metrics?.r2 === "number" ? run.metrics.r2.toFixed(3) : "—"}
                    </span>
                  </div>
                  <div className="col-span-1 flex items-center justify-end">
                    <span className="text-sm tabular-nums" style={{ fontFamily: "'JetBrains Mono', monospace", color: typeof run.metrics?.mae === "number" ? "oklch(0.72 0.18 160)" : "oklch(0.65 0.015 250)" }}>
                      {typeof run.metrics?.mae === "number" ? run.metrics.mae.toFixed(3) : "—"}
                    </span>
                  </div>
                  <div className="col-span-1 flex items-center justify-end">
                    <span className="text-sm tabular-nums text-muted-foreground" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
                      {run.metrics?.train_size ?? "—"}
                    </span>
                  </div>
                  <div className="col-span-1 flex items-center justify-end">
                    <span className="text-sm tabular-nums text-muted-foreground" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
                      {run.metrics?.test_size ?? "—"}
                    </span>
                  </div>
                  <div className="col-span-2 flex items-center justify-end">
                    <span className="text-xs text-muted-foreground" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
                      {formatDate(run.created_at)}
                    </span>
                  </div>
                </button>

                {/* Expanded detail */}
                {expandedId === run.id && (
                  <div className="px-5 pb-5 pt-3 bg-muted/20 border-b border-border">
                    <div className="grid grid-cols-4 gap-4">
                      <div className="labpilot-card p-4">
                        <div className="flex items-center gap-2 mb-3">
                          <Database className="w-4 h-4 text-muted-foreground" />
                          <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Dataset</span>
                        </div>
                        <div className="text-xs text-foreground break-all" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
                          {run.dataset_path}
                        </div>
                      </div>
                      <div className="labpilot-card p-4">
                        <div className="flex items-center gap-2 mb-3">
                          <Target className="w-4 h-4 text-muted-foreground" />
                          <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Target</span>
                        </div>
                        <div className="text-xs text-foreground" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
                          {run.target_column}
                        </div>
                      </div>
                      <div className="labpilot-card p-4">
                        <div className="flex items-center gap-2 mb-3">
                          <BarChart2 className="w-4 h-4 text-muted-foreground" />
                          <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Metrics</span>
                        </div>
                        {typeof run.metrics?.r2 === "number" ? (
                          <div className="space-y-1">
                            <div className="flex justify-between">
                              <span className="text-xs text-muted-foreground">R²</span>
                              <span className="text-xs font-semibold" style={{ color: "oklch(0.52 0.22 260)", fontFamily: "'JetBrains Mono', monospace" }}>{run.metrics?.r2?.toFixed(3)}</span>
                            </div>
                            <div className="flex justify-between">
                              <span className="text-xs text-muted-foreground">MAE</span>
                              <span className="text-xs font-semibold" style={{ color: "oklch(0.72 0.18 160)", fontFamily: "'JetBrains Mono', monospace" }}>{run.metrics?.mae?.toFixed(3)}</span>
                            </div>
                            <div className="flex justify-between">
                              <span className="text-xs text-muted-foreground">Train / Test</span>
                              <span className="text-xs font-semibold text-muted-foreground" style={{ fontFamily: "'JetBrains Mono', monospace" }}>{run.metrics?.train_size ?? "—"} / {run.metrics?.test_size ?? "—"}</span>
                            </div>
                          </div>
                        ) : (
                          <div className="flex items-center gap-1.5 text-xs text-blue-500">
                            <Loader2 className="w-3 h-3 animate-spin" /> Training in progress…
                          </div>
                        )}
                      </div>
                      <div className="labpilot-card p-4">
                        <div className="flex items-center gap-2 mb-3">
                          <Layers className="w-4 h-4 text-muted-foreground" />
                          <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Artifact</span>
                        </div>
                        {run.model_path ? (
                          <div className="text-xs text-foreground break-all" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
                            {run.model_path}
                          </div>
                        ) : (
                          <div className="text-xs text-muted-foreground">Not yet saved</div>
                        )}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
    </AppLayout>
  );
}
