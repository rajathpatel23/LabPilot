import { useEffect, useMemo, useState } from "react";
import AppLayout from "@/components/AppLayout";
import { Button } from "@/components/ui/button";
import { API_BASE_URL, apiGet, apiPost, type ApiConversation, type ApiSession, type ApiTrainingRun } from "@/lib/api";
import { toast } from "sonner";
import { useLocation } from "wouter";

const DEFAULT_CONDITIONS = {
  Reactant_1_Short_Hand: "1c, 6-OTf-Q",
  Reactant_1_eq: 1,
  Reactant_1_mmol: 0.0004,
  Reactant_2_Name: "2b, Boronic Ester",
  Reactant_2_eq: 1,
  Catalyst_1_Short_Hand: "Pd(OAc)2",
  Catalyst_1_eq: 0.0625,
  Ligand_Short_Hand: "CataCXium A",
  Ligand_eq: 0.125,
  Reagent_1_Short_Hand: "CsF",
  Reagent_1_eq: 2.5,
  Solvent_1_Short_Hand: "MeCN",
};

export default function InputPage() {
  const [, navigate] = useLocation();
  const [sessions, setSessions] = useState<ApiSession[]>([]);
  const [sessionId, setSessionId] = useState("");
  const [observedYield, setObservedYield] = useState("85.0");
  const [notes, setNotes] = useState("manual lab outcome");
  const [conditionsJson, setConditionsJson] = useState(JSON.stringify(DEFAULT_CONDITIONS, null, 2));
  const [submitting, setSubmitting] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [bootstrapping, setBootstrapping] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [uploadedPath, setUploadedPath] = useState("");
  const [targetColumn, setTargetColumn] = useState("Product_Yield_PCT_Area_UV");

  useEffect(() => {
    apiGet<ApiSession[]>("/api/sessions")
      .then((rows) => {
        setSessions(rows);
        if (rows.length > 0) setSessionId(rows[0].id);
      })
      .catch(() => toast.error("Failed to load sessions."));
  }, []);

  const selected = useMemo(() => sessions.find((s) => s.id === sessionId) ?? null, [sessions, sessionId]);

  function inferTargetCandidates(filename: string): string[] {
    const f = filename.toLowerCase();
    if (f.includes("doyle")) return ["yield", "Yield", "Product_Yield_PCT_Area_UV"];
    return ["Product_Yield_PCT_Area_UV", "yield", "Yield"];
  }

  async function uploadDatasetAndGetPath(): Promise<string> {
    if (!file) {
      toast.error("Choose a CSV/XLSX file first.");
      throw new Error("No file selected.");
    }
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${API_BASE_URL}/api/datasets/upload`, {
      method: "POST",
      body: form,
    });
    const text = await res.text();
    if (!res.ok) {
      throw new Error(text || `Upload failed (${res.status})`);
    }
    const parsed = text ? JSON.parse(text) : {};
    const path = String(parsed.stored_path ?? "");
    if (!path) throw new Error("Upload succeeded but no stored_path returned.");
    setUploadedPath(path);
    return path;
  }

  async function handleUpload() {
    setUploading(true);
    try {
      const path = await uploadDatasetAndGetPath();
      if (file) {
        const inferred = inferTargetCandidates(file.name)[0];
        setTargetColumn(inferred);
      }
      toast.success(`Dataset uploaded: ${path}`);
    } catch (e) {
      toast.error(`Upload failed: ${String(e)}`);
    } finally {
      setUploading(false);
    }
  }

  async function handleUploadTrainAndStartChat() {
    setBootstrapping(true);
    try {
      // 1) Upload dataset
      const path = uploadedPath || (await uploadDatasetAndGetPath());
      toast.success("Dataset uploaded. Starting training...");

      // 2) Train model (synchronous backend call: waits until run finishes)
      const candidates = file ? inferTargetCandidates(file.name) : [targetColumn, "Product_Yield_PCT_Area_UV", "yield"];
      const targetCandidates = [targetColumn, ...candidates].filter((v, i, arr) => Boolean(v) && arr.indexOf(v) === i);
      let trainingRun: ApiTrainingRun | null = null;
      for (const cand of targetCandidates) {
        const run = await apiPost<ApiTrainingRun>("/api/training/runs", {
          dataset_path: path,
          target_column: cand,
          features: [],
          output_name: `surrogate_quick_${Date.now()}`,
        });
        if (run.status === "completed" && run.model_path) {
          trainingRun = run;
          setTargetColumn(cand);
          break;
        }
      }
      if (!trainingRun?.model_path) {
        throw new Error(`Training failed. Try setting target column manually (attempted: ${targetCandidates.join(", ")}).`);
      }
      toast.success("Training completed. Creating session + chat...");

      // 3) Create linked conversation
      const conv = await apiPost<ApiConversation>("/api/conversations", {
        title: `Campaign ${file?.name ?? "uploaded dataset"} ${new Date().toLocaleString()}`,
      });

      // 4) Create session on trained model
      const sessionPayload = await apiPost<{ id: string; conversation_id?: string | null }>("/api/sessions", {
        title: `Session ${file?.name ?? "uploaded dataset"}`,
        conversation_id: conv.id,
        dataset_path: path,
        model_path: trainingRun.model_path,
        budget: 20,
        top_k: 5,
        use_llm: true,
        use_tavily: true,
      });
      if (!sessionPayload?.id) {
        throw new Error("Session creation failed.");
      }

      // 5) Seed first assistant recommendation in the conversation thread.
      await apiPost(`/api/conversations/${conv.id}/messages`, {
        content: "Recommend a simple starter experiment and one follow-up plan based on likely outcomes.",
        data_path: path,
        model_path: trainingRun.model_path,
        top_k: 5,
        use_llm: true,
        use_tavily: true,
      });

      const rows = await apiGet<ApiSession[]>("/api/sessions");
      setSessions(rows);
      setSessionId(sessionPayload.id);
      toast.success("Ready. Opening chat with your trained model.");
      navigate(`/conversations/${conv.id}`);
    } catch (e) {
      toast.error(`Quick start failed: ${String(e)}`);
    } finally {
      setBootstrapping(false);
    }
  }

  async function handleSubmit() {
    if (!sessionId) {
      toast.error("Select a session.");
      return;
    }
    let conditions: Record<string, unknown>;
    try {
      conditions = JSON.parse(conditionsJson);
    } catch {
      toast.error("Conditions must be valid JSON.");
      return;
    }
    setSubmitting(true);
    try {
      const payload = await apiPost<{ session: ApiSession; remaining_budget: number }>(`/api/sessions/${sessionId}/submit-result`, {
        observed_yield: Number(observedYield),
        notes,
        conditions,
      });
      toast.success(`Result submitted. Remaining budget: ${payload.remaining_budget}`);
      const nextConversationId = payload.session?.conversation_id;
      if (nextConversationId) {
        toast.success("Opening linked conversation with follow-up recommendation...");
        navigate(`/conversations/${nextConversationId}`);
        return;
      }
      const rows = await apiGet<ApiSession[]>("/api/sessions");
      setSessions(rows);
    } catch (e) {
      toast.error(`Failed to submit result: ${String(e)}`);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AppLayout title="Input Outcome" subtitle="Step 3: submit observed outcome to an existing trained session, then continue in chat">
      <div className="p-8 space-y-5 max-w-4xl">
        <div className="labpilot-card p-5 space-y-3">
          <label className="text-xs text-muted-foreground block mb-2">Optional: Upload New Dataset for Model Training (.csv, .xlsx, .xls)</label>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <input
              type="file"
              accept=".csv,.xlsx,.xls"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="text-sm rounded-lg border border-border bg-background px-3 py-2"
            />
            <Button variant="outline" onClick={handleUpload} disabled={uploading || !file}>
              {uploading ? "Uploading..." : "Upload Dataset"}
            </Button>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <input
              value={targetColumn}
              onChange={(e) => setTargetColumn(e.target.value)}
              className="rounded-lg border border-border bg-background px-3 py-2 text-sm"
              placeholder="Target column (e.g., Product_Yield_PCT_Area_UV)"
            />
            <div />
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <Button
              variant="outline"
              disabled={!uploadedPath}
              onClick={() => navigate(`/training?dataset=${encodeURIComponent(uploadedPath)}`)}
            >
              Train This Dataset
            </Button>
            <Button onClick={handleUploadTrainAndStartChat} disabled={bootstrapping || (!file && !uploadedPath)}>
              {bootstrapping ? "Running end-to-end..." : "Upload + Train + Start Chat"}
            </Button>
          </div>
          {uploadedPath ? (
            <div className="mt-2 text-xs text-muted-foreground">
              Stored at: <code>{uploadedPath}</code>. You can either train manually from Training page or use one-click quick start.
            </div>
          ) : null}
        </div>

        <div className="labpilot-card p-5 grid grid-cols-2 gap-4">
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
                  {s.title} ({s.status}) — {s.id.slice(0, 8)}
                </option>
              ))}
            </select>
            {selected && (
              <div className="text-xs text-muted-foreground mt-2">
                Steps: {selected.steps_completed}/{selected.budget} · Conversation: {selected.conversation_id ?? "not linked"}
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
            <label className="text-xs text-muted-foreground block mt-3 mb-1">Notes</label>
            <input
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
            />
          </div>
        </div>

        <div className="labpilot-card p-5">
          <label className="text-xs text-muted-foreground block mb-2">Conditions JSON</label>
          <textarea
            value={conditionsJson}
            onChange={(e) => setConditionsJson(e.target.value)}
            className="w-full min-h-[260px] rounded-lg border border-border bg-background px-3 py-2 text-xs font-mono"
          />
          <div className="mt-3 flex justify-end">
            <Button onClick={handleSubmit} disabled={submitting || !sessionId}>
              {submitting ? "Submitting…" : "Submit Outcome"}
            </Button>
          </div>
        </div>
      </div>
    </AppLayout>
  );
}
