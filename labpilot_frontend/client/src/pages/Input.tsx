import { useEffect, useMemo, useState } from "react";
import AppLayout from "@/components/AppLayout";
import { Button } from "@/components/ui/button";
import {
  API_BASE_URL,
  apiGet,
  apiPost,
  type ApiConversation,
  type ApiDataset,
  type ApiSession,
  type ApiTrainingRun,
} from "@/lib/api";
import { toast } from "sonner";
import { useLocation } from "wouter";
import { Upload, Database, Brain, MessageSquare, ChevronRight, Loader2 } from "lucide-react";

export default function InputPage() {
  const [, navigate] = useLocation();

  // Data
  const [datasets, setDatasets] = useState<ApiDataset[]>([]);
  const [sessions, setSessions] = useState<ApiSession[]>([]);

  // Upload state
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);

  // Dataset selection
  const [selectedDatasetId, setSelectedDatasetId] = useState("");
  const [targetColumn, setTargetColumn] = useState("");

  // Training
  const [training, setTraining] = useState(false);
  const [datasetModels, setDatasetModels] = useState<ApiTrainingRun[]>([]);
  const [selectedModelPath, setSelectedModelPath] = useState("");

  // Quick pipeline
  const [bootstrapping, setBootstrapping] = useState(false);

  // Submit outcome
  const [sessionId, setSessionId] = useState("");
  const [observedYield, setObservedYield] = useState("85.0");
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    apiGet<ApiDataset[]>("/api/datasets").then(setDatasets).catch(() => {});
    apiGet<ApiSession[]>("/api/sessions").then((rows) => {
      setSessions(rows);
      if (rows.length > 0) setSessionId(rows[0].id);
    }).catch(() => {});
  }, []);

  const selectedDataset = useMemo(
    () => datasets.find((d) => d.id === selectedDatasetId) ?? null,
    [datasets, selectedDatasetId],
  );

  const selectedSession = useMemo(
    () => sessions.find((s) => s.id === sessionId) ?? null,
    [sessions, sessionId],
  );

  // When dataset selection changes, load its models and set target candidate
  useEffect(() => {
    if (!selectedDatasetId) return;
    apiGet<ApiTrainingRun[]>(`/api/datasets/${selectedDatasetId}/models`)
      .then((models) => {
        setDatasetModels(models);
        if (models.length > 0 && models[0].model_path) {
          setSelectedModelPath(models[0].model_path);
        } else {
          setSelectedModelPath("");
        }
      })
      .catch(() => setDatasetModels([]));
    const ds = datasets.find((d) => d.id === selectedDatasetId);
    if (ds?.target_candidates?.length) {
      setTargetColumn(ds.target_candidates[0]);
    }
  }, [selectedDatasetId, datasets]);

  // ---- Handlers ----

  async function handleUpload() {
    if (!file) { toast.error("Choose a file first."); return; }
    setUploading(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch(`${API_BASE_URL}/api/datasets/upload`, { method: "POST", body: form });
      const text = await res.text();
      if (!res.ok) throw new Error(text || `Upload failed (${res.status})`);
      const parsed = JSON.parse(text);
      const ds = parsed.dataset as ApiDataset | undefined;
      toast.success(`Dataset uploaded: ${parsed.filename}`);
      const refreshed = await apiGet<ApiDataset[]>("/api/datasets");
      setDatasets(refreshed);
      if (ds?.id) setSelectedDatasetId(ds.id);
    } catch (e) {
      toast.error(`Upload failed: ${String(e)}`);
    } finally {
      setUploading(false);
    }
  }

  async function handleTrain() {
    if (!selectedDataset || !targetColumn) { toast.error("Select dataset and target column."); return; }
    setTraining(true);
    try {
      const run = await apiPost<ApiTrainingRun>("/api/training/runs", {
        dataset_path: selectedDataset.stored_path,
        target_column: targetColumn,
        features: [],
        output_name: `surrogate_${selectedDataset.name}_${Date.now()}`,
      });
      if (run.status === "completed" && run.model_path) {
        toast.success(`Model trained (R²=${run.metrics?.r2?.toFixed(3) ?? "?"}).`);
        setSelectedModelPath(run.model_path);
        const models = await apiGet<ApiTrainingRun[]>(`/api/datasets/${selectedDatasetId}/models`);
        setDatasetModels(models);
      } else {
        toast.error("Training failed. Check target column.");
      }
    } catch (e) {
      toast.error(`Training error: ${String(e)}`);
    } finally {
      setTraining(false);
    }
  }

  async function handleStartChat() {
    if (!selectedDataset || !selectedModelPath) { toast.error("Train a model first."); return; }
    setBootstrapping(true);
    try {
      const conv = await apiPost<ApiConversation>("/api/conversations", {
        title: `${selectedDataset.name} — ${new Date().toLocaleString()}`,
      });
      await apiPost("/api/sessions", {
        title: `Session ${selectedDataset.name}`,
        conversation_id: conv.id,
        dataset_path: selectedDataset.stored_path,
        model_path: selectedModelPath,
        budget: 20,
        top_k: 5,
        use_llm: true,
        use_tavily: true,
      });
      await apiPost(`/api/conversations/${conv.id}/messages`, {
        content: "Recommend a starter experiment and one follow-up plan.",
        data_path: selectedDataset.stored_path,
        model_path: selectedModelPath,
        top_k: 5,
        use_llm: false,
        use_tavily: false,
      });
      toast.success("Session created. Opening chat...");
      navigate(`/conversations/${conv.id}`);
    } catch (e) {
      toast.error(`Failed: ${String(e)}`);
    } finally {
      setBootstrapping(false);
    }
  }

  async function handleSubmitOutcome() {
    if (!sessionId) { toast.error("Select a session."); return; }
    setSubmitting(true);
    try {
      const payload = await apiPost<{ session: ApiSession; remaining_budget: number }>(
        `/api/sessions/${sessionId}/submit-result`,
        { observed_yield: Number(observedYield), notes, conditions: {} },
      );
      toast.success(`Submitted. Budget remaining: ${payload.remaining_budget}`);
      if (payload.session?.conversation_id) {
        navigate(`/conversations/${payload.session.conversation_id}`);
        return;
      }
      const rows = await apiGet<ApiSession[]>("/api/sessions");
      setSessions(rows);
    } catch (e) {
      toast.error(`Submit failed: ${String(e)}`);
    } finally {
      setSubmitting(false);
    }
  }

  // ---- Render ----
  return (
    <AppLayout title="New Experiment" subtitle="Upload data → train model → start optimization chat">
      <div className="p-8 space-y-6 max-w-5xl">

        {/* ── Step 1: Upload ── */}
        <div className="labpilot-card p-6">
          <div className="flex items-center gap-2 mb-4">
            <div className="w-7 h-7 rounded-full bg-blue-100 flex items-center justify-center">
              <Upload className="w-3.5 h-3.5 text-blue-600" />
            </div>
            <h3 className="font-semibold text-sm" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
              Step 1 — Upload Dataset
            </h3>
          </div>
          <div className="flex items-center gap-4">
            <input
              type="file"
              accept=".csv,.xlsx,.xls"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="text-sm flex-1"
            />
            <Button onClick={handleUpload} disabled={uploading || !file} size="sm">
              {uploading ? <Loader2 className="w-3.5 h-3.5 animate-spin mr-1" /> : null}
              Upload
            </Button>
          </div>
        </div>

        {/* ── Step 2: Select dataset + train ── */}
        <div className="labpilot-card p-6">
          <div className="flex items-center gap-2 mb-4">
            <div className="w-7 h-7 rounded-full bg-violet-100 flex items-center justify-center">
              <Database className="w-3.5 h-3.5 text-violet-600" />
            </div>
            <h3 className="font-semibold text-sm" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
              Step 2 — Select Dataset &amp; Train Model
            </h3>
          </div>

          <div className="grid grid-cols-3 gap-4 mb-4">
            <div>
              <label className="text-xs text-muted-foreground block mb-1">Dataset</label>
              <select
                value={selectedDatasetId}
                onChange={(e) => setSelectedDatasetId(e.target.value)}
                className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
              >
                <option value="">Choose dataset…</option>
                {datasets.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name} ({d.num_rows ?? "?"} rows, {d.num_cols ?? "?"} cols)
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-xs text-muted-foreground block mb-1">Target Column</label>
              {selectedDataset?.target_candidates?.length ? (
                <select
                  value={targetColumn}
                  onChange={(e) => setTargetColumn(e.target.value)}
                  className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
                >
                  {selectedDataset.target_candidates.map((c) => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                  {selectedDataset.columns?.filter((c) => !selectedDataset.target_candidates?.includes(c)).map((c) => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </select>
              ) : (
                <input
                  value={targetColumn}
                  onChange={(e) => setTargetColumn(e.target.value)}
                  placeholder="e.g. yield or Product_Yield_PCT_Area_UV"
                  className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
                />
              )}
            </div>
            <div className="flex items-end">
              <Button onClick={handleTrain} disabled={training || !selectedDatasetId || !targetColumn} size="sm" className="gap-1">
                {training ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Brain className="w-3.5 h-3.5" />}
                Train Model
              </Button>
            </div>
          </div>

          {/* Trained models for this dataset */}
          {datasetModels.length > 0 && (
            <div className="mt-3">
              <label className="text-xs text-muted-foreground block mb-1">Trained Models</label>
              <div className="space-y-1">
                {datasetModels.map((m) => (
                  <label
                    key={m.id}
                    className={`flex items-center gap-2 px-3 py-2 rounded-lg border cursor-pointer text-xs transition-colors ${
                      selectedModelPath === m.model_path ? "border-blue-400 bg-blue-50" : "border-border hover:bg-muted/30"
                    }`}
                  >
                    <input
                      type="radio"
                      name="model"
                      checked={selectedModelPath === m.model_path}
                      onChange={() => setSelectedModelPath(m.model_path ?? "")}
                      className="accent-blue-600"
                    />
                    <span className="font-mono">{m.model_path?.split("/").pop() ?? m.id.slice(0, 8)}</span>
                    <span className="text-muted-foreground">
                      R²={m.metrics?.r2?.toFixed(3) ?? "?"} · MAE={m.metrics?.mae?.toFixed(2) ?? "?"} · {m.target_column}
                    </span>
                  </label>
                ))}
              </div>
            </div>
          )}

          {selectedModelPath && (
            <div className="mt-4 flex items-center gap-3">
              <ChevronRight className="w-4 h-4 text-muted-foreground" />
              <Button onClick={handleStartChat} disabled={bootstrapping} size="sm" className="gap-1">
                {bootstrapping ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <MessageSquare className="w-3.5 h-3.5" />}
                Create Session &amp; Open Chat
              </Button>
            </div>
          )}
        </div>

        {/* ── Step 3: Submit outcome to existing session ── */}
        <div className="labpilot-card p-6">
          <div className="flex items-center gap-2 mb-4">
            <div className="w-7 h-7 rounded-full bg-amber-100 flex items-center justify-center">
              <span className="text-amber-700 text-xs font-bold">3</span>
            </div>
            <h3 className="font-semibold text-sm" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
              Step 3 — Submit Observed Outcome
            </h3>
          </div>

          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="text-xs text-muted-foreground block mb-1">Session</label>
              <select
                value={sessionId}
                onChange={(e) => setSessionId(e.target.value)}
                className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
              >
                <option value="">Select session…</option>
                {sessions.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.title} ({s.status}) — step {s.steps_completed}/{s.budget}
                  </option>
                ))}
              </select>
              {selectedSession && (
                <div className="text-[11px] text-muted-foreground mt-1">
                  Dataset: {selectedSession.dataset_path.split("/").pop()}
                </div>
              )}
            </div>
            <div>
              <label className="text-xs text-muted-foreground block mb-1">Observed Yield</label>
              <input
                type="number"
                value={observedYield}
                onChange={(e) => setObservedYield(e.target.value)}
                className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="text-xs text-muted-foreground block mb-1">Notes</label>
              <input
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Optional notes"
                className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
              />
            </div>
          </div>
          <div className="mt-4 flex justify-end">
            <Button onClick={handleSubmitOutcome} disabled={submitting || !sessionId} size="sm">
              {submitting ? <Loader2 className="w-3.5 h-3.5 animate-spin mr-1" /> : null}
              Submit &amp; Continue in Chat
            </Button>
          </div>
        </div>
      </div>
    </AppLayout>
  );
}
