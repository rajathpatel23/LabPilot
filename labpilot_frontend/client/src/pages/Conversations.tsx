import { useEffect, useMemo, useState } from "react";
import AppLayout from "@/components/AppLayout";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Bot, Brain, CheckCircle2, Cpu, Layers, Loader2, MessageSquare, Plus, Send, Star, User } from "lucide-react";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import { apiGet, apiPost, type ApiConversation, type ApiMessage } from "@/lib/api";
import { useLocation } from "wouter";

const DEFAULT_DATASET = "data/Suzuki-Miyaura/aap9112_Data_File_S1.xlsx";
const DEFAULT_MODEL = "artifacts/surrogate_suzuki.joblib";

function formatTime(iso: string) {
  return new Date(iso).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" });
}
function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function JsonPanel({ data }: { data: unknown }) {
  return (
    <pre className="text-xs whitespace-pre-wrap break-all rounded-lg border border-border p-3 bg-muted/30" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
      {JSON.stringify(data ?? {}, null, 2)}
    </pre>
  );
}

type AnyObj = Record<string, unknown>;

const SUBSCRIPT_MAP: Record<string, string> = {
  "0": "₀",
  "1": "₁",
  "2": "₂",
  "3": "₃",
  "4": "₄",
  "5": "₅",
  "6": "₆",
  "7": "₇",
  "8": "₈",
  "9": "₉",
};

const FIELD_LABELS: Record<string, string> = {
  Reactant_1_Short_Hand: "Reactant 1",
  Reactant_2_Name: "Reactant 2",
  Catalyst_1_Short_Hand: "Catalyst",
  Ligand_Short_Hand: "Ligand",
  Reagent_1_Short_Hand: "Base/Reagent",
  Solvent_1_Short_Hand: "Solvent",
  Reactant_1_eq: "Reactant 1 eq",
  Reactant_2_eq: "Reactant 2 eq",
  Catalyst_1_eq: "Catalyst eq",
  Ligand_eq: "Ligand eq",
  Reagent_1_eq: "Reagent eq",
  Reactant_1_mmol: "Reactant 1 mmol",
  predicted_yield: "Predicted Yield",
  predicted_uncertainty: "Uncertainty",
  ranking_method: "Ranking",
  ucb_score: "UCB Score",
};

function toSubscriptDigits(input: string): string {
  return input.replace(/\d/g, (d) => SUBSCRIPT_MAP[d] ?? d);
}

function formatChemString(input: string): string {
  // Convert common chemistry digit notation to subscripts: H2O -> H₂O, Pd(OAc)2 -> Pd(OAc)₂.
  return input.replace(/([A-Za-z\)])(\d+)/g, (_m, left: string, digits: string) => `${left}${toSubscriptDigits(digits)}`);
}

function formatFieldLabel(label: string): string {
  if (FIELD_LABELS[label]) return FIELD_LABELS[label];
  return label.replaceAll("_", " ");
}

function formatChemValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") return String(value);
  if (typeof value === "string") return formatChemString(value);
  return String(value);
}

function ValuePill({ label, value }: { label: string; value: unknown }) {
  return (
    <div className="rounded-md border border-border bg-muted/20 px-2 py-1">
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{formatFieldLabel(label)}</div>
      <div className="text-xs text-foreground" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
        {formatChemValue(value)}
      </div>
    </div>
  );
}

function RankBadge({ rank }: { rank: number }) {
  if (rank === 1) {
    return (
      <div className="w-7 h-7 rounded-full flex items-center justify-center" style={{ background: "oklch(0.85 0.12 80)" }}>
        <Star className="w-3.5 h-3.5" style={{ color: "oklch(0.45 0.18 80)" }} />
      </div>
    );
  }
  return (
    <div className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold" style={{ background: "oklch(0.88 0.05 240)", color: "oklch(0.45 0.08 240)" }}>
      #{rank}
    </div>
  );
}

function ConfidenceBar({ uncertainty }: { uncertainty: number | null }) {
  if (uncertainty === null || Number.isNaN(uncertainty)) {
    return <span className="text-xs text-muted-foreground">n/a</span>;
  }
  const confidence = Math.max(5, Math.min(98, Math.round(100 - uncertainty * 3)));
  const color =
    confidence >= 80 ? "oklch(0.72 0.18 160)" :
    confidence >= 65 ? "oklch(0.72 0.18 80)" :
    "oklch(0.62 0.20 300)";
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden">
        <div className="h-full rounded-full" style={{ width: `${confidence}%`, background: color }} />
      </div>
      <span className="text-[10px] font-mono" style={{ color }}>{confidence}%</span>
    </div>
  );
}

function ReasoningText({ text }: { text: string }) {
  const paragraphs = text.split(/\n\n+/).filter(Boolean);
  return (
    <div className="space-y-2">
      {paragraphs.map((p, i) => (
        <p key={i} className="text-xs leading-relaxed text-foreground whitespace-pre-wrap">
          {formatChemString(p)}
        </p>
      ))}
    </div>
  );
}

export default function Conversations() {
  const [location, navigate] = useLocation();
  const [conversations, setConversations] = useState<ApiConversation[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ApiMessage[]>([]);
  const [input, setInput] = useState("");
  const [metaTab, setMetaTab] = useState<"recommendation" | "reasoning" | "literature" | "trace">("recommendation");
  const [sending, setSending] = useState(false);
  const [loadingConversations, setLoadingConversations] = useState(true);
  const routeConversationId = useMemo(() => {
    const m = location.match(/^\/conversations\/([^/]+)$/);
    return m ? decodeURIComponent(m[1]) : null;
  }, [location]);

  async function loadConversations(selectLatest = false) {
    const data = await apiGet<ApiConversation[]>("/api/conversations");
    setConversations(data);
    if (routeConversationId && data.some((c) => c.id === routeConversationId)) {
      setSelectedId(routeConversationId);
      return;
    }
    if (data.length > 0 && (selectLatest || !selectedId)) {
      setSelectedId(data[0].id);
    }
  }

  async function loadMessages(conversationId: string) {
    const data = await apiGet<ApiMessage[]>(`/api/conversations/${conversationId}/messages`);
    setMessages(data);
  }

  useEffect(() => {
    loadConversations(true)
      .catch(() => toast.error("Failed to load conversations."))
      .finally(() => setLoadingConversations(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!selectedId) return;
    loadMessages(selectedId).catch(() => toast.error("Failed to load messages."));
  }, [selectedId]);

  useEffect(() => {
    if (!routeConversationId) return;
    setSelectedId(routeConversationId);
  }, [routeConversationId]);

  useEffect(() => {
    if (!selectedId) return;
    const timer = window.setInterval(() => {
      loadMessages(selectedId).catch(() => {
        // Keep polling resilient; avoid noisy repeated toasts.
      });
    }, 4000);
    return () => window.clearInterval(timer);
  }, [selectedId]);

  const selectedConv = useMemo(
    () => conversations.find((c) => c.id === selectedId) ?? null,
    [conversations, selectedId]
  );
  // Show metadata from the most recent assistant message that actually carries
  // recommendation, literature, or evidence data — not just any assistant message.
  // This prevents follow-up smalltalk/status responses from wiping the panel.
  const lastRichMsg = useMemo(() => {
    return [...messages].reverse().find((m) => {
      if (m.role !== "assistant" || !m.metadata) return false;
      const md = m.metadata as AnyObj;
      return md.recommendation || md.evidence || md.literature_explain;
    });
  }, [messages]);
  const lastAssistantMsg = lastRichMsg ?? [...messages].reverse().find((m) => m.role === "assistant" && m.metadata) ?? null;
  const meta = (lastAssistantMsg?.metadata ?? {}) as AnyObj;
  const recommendation = (meta.recommendation as AnyObj | undefined) ?? {};
  const reasoning = (meta.reasoning as AnyObj | undefined) ?? {};
  const evidence = (meta.evidence as AnyObj | undefined) ?? {};
  const literatureExplain = (meta.literature_explain as AnyObj | undefined) ?? {};
  const rankedCandidates = ((recommendation.ranked_candidates as AnyObj[] | undefined) ?? []).slice(0, 5);

  const handleSend = async () => {
    if (!input.trim() || !selectedId) return;
    setSending(true);
    const userText = input.trim();
    try {
      const assistantMsg = await apiPost<ApiMessage>(`/api/conversations/${selectedId}/messages`, {
        content: userText,
        data_path: DEFAULT_DATASET,
        model_path: DEFAULT_MODEL,
        top_k: 5,
        use_llm: true,
        use_tavily: true,
      });

      // Immediate local update so chat never appears empty even if list refresh lags.
      setMessages((prev) => [
        ...prev,
        {
          id: `temp-user-${Date.now()}`,
          role: "user",
          content: userText,
          created_at: new Date().toISOString(),
        },
        assistantMsg,
      ]);

      setInput("");
      await loadMessages(selectedId);
      await loadConversations(false);
      toast.success("Agent response received.");
    } catch (e) {
      toast.error(`Failed to send message: ${String(e)}`);
    } finally {
      setSending(false);
    }
  };

  const handleQuickStart = async () => {
    setInput("Recommend a simple starter experiment and one follow-up plan based on likely outcomes.");
    if (!selectedId) return;
    setSending(true);
    try {
      const assistantMsg = await apiPost<ApiMessage>(`/api/conversations/${selectedId}/messages`, {
        content: "Recommend a simple starter experiment and one follow-up plan based on likely outcomes.",
        data_path: DEFAULT_DATASET,
        model_path: DEFAULT_MODEL,
        top_k: 5,
        use_llm: true,
        use_tavily: true,
      });
      setMessages((prev) => [...prev, assistantMsg]);
      setInput("");
      await loadMessages(selectedId);
      await loadConversations(false);
      toast.success("Starter recommendation ready.");
    } catch (e) {
      toast.error(`Failed to generate starter recommendation: ${String(e)}`);
    } finally {
      setSending(false);
    }
  };

  const handleNewConversation = async () => {
    try {
      const created = await apiPost<ApiConversation>("/api/conversations", {
        title: `Campaign ${new Date().toLocaleString()}`,
      });
      await loadConversations(false);
      setSelectedId(created.id);
      navigate(`/conversations/${created.id}`);
      setMessages([]);
      toast.success("Conversation created.");
    } catch (e) {
      toast.error(`Failed to create conversation: ${String(e)}`);
    }
  };

  return (
    <AppLayout title="Conversations" subtitle="Threaded AI copilot for experiment recommendations">
      <div className="flex h-full" style={{ height: "calc(100vh - 73px)" }}>
        {/* Left: Thread List */}
        <div
          className="w-64 flex-shrink-0 border-r border-border flex flex-col"
          style={{ background: "oklch(0.99 0.002 240)" }}
        >
          <div className="p-3 border-b border-border">
            <Button
              size="sm"
              className="w-full gap-2 text-xs"
              onClick={handleNewConversation}
            >
              <Plus className="w-3.5 h-3.5" />
              New Conversation
            </Button>
          </div>
          <ScrollArea className="flex-1">
            <div className="p-2 space-y-1">
              {conversations.map((c) => (
                <button
                  key={c.id}
                  onClick={() => {
                    setSelectedId(c.id);
                    navigate(`/conversations/${c.id}`);
                  }}
                  className={cn(
                    "w-full text-left p-3 rounded-lg transition-all duration-100",
                    selectedId === c.id
                      ? "bg-blue-50 border border-blue-200"
                      : "hover:bg-muted/60"
                  )}
                >
                  <div className="flex items-start gap-2">
                    <MessageSquare
                      className="w-3.5 h-3.5 mt-0.5 flex-shrink-0"
                      style={{ color: selectedId === c.id ? "oklch(0.52 0.22 260)" : "oklch(0.55 0.015 250)" }}
                    />
                    <div className="min-w-0">
                      <div
                        className={cn("text-xs font-medium truncate", selectedId === c.id ? "text-blue-700" : "text-foreground")}
                        style={{ fontFamily: "'Inter', sans-serif" }}
                      >
                        {c.title}
                      </div>
                      <div className="text-xs text-muted-foreground truncate mt-0.5 leading-relaxed">
                        Thread history
                      </div>
                      <div
                        className="text-xs text-muted-foreground mt-1"
                        style={{ fontFamily: "'JetBrains Mono', monospace" }}
                      >
                        {formatDate(c.updated_at)}
                      </div>
                    </div>
                  </div>
                </button>
              ))}
              {!loadingConversations && conversations.length === 0 && (
                <div className="px-3 py-6 text-xs text-muted-foreground">No conversations yet. Create one to begin.</div>
              )}
            </div>
          </ScrollArea>
        </div>

        {/* Center: Chat Timeline */}
        <div className="flex-1 flex flex-col min-w-0">
          {/* Thread header */}
          <div className="px-5 py-3 border-b border-border bg-card flex items-center gap-3">
            <div className="w-7 h-7 rounded-full bg-blue-100 flex items-center justify-center">
              <MessageSquare className="w-3.5 h-3.5 text-blue-600" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-sm font-semibold text-foreground truncate" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
                {selectedConv?.title ?? "No conversation selected"}
              </div>
              <div className="text-xs text-muted-foreground">{messages.length} messages</div>
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              <code className="text-[10px] text-muted-foreground px-2 py-0.5 rounded bg-muted" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
                data: {DEFAULT_DATASET.split("/").pop()}
              </code>
              <code className="text-[10px] text-muted-foreground px-2 py-0.5 rounded bg-muted" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
                model: {DEFAULT_MODEL.split("/").pop()}
              </code>
            </div>
          </div>

          {/* Messages */}
          <ScrollArea className="flex-1 px-5 py-4">
            {messages.length === 0 && (
              <div className="max-w-2xl rounded-xl border border-dashed border-border bg-muted/20 p-4 mb-4">
                <div className="text-sm font-medium mb-1">Start With a Simple Recommendation</div>
                <div className="text-xs text-muted-foreground mb-3">
                  Ask LabPilot for one starter experiment and a follow-up decision rule based on observed yield.
                </div>
                <Button size="sm" onClick={handleQuickStart} disabled={sending}>
                  {sending ? <Loader2 className="w-3.5 h-3.5 animate-spin mr-2" /> : null}
                  Recommend Starter Experiment
                </Button>
              </div>
            )}
            <div className="space-y-5 max-w-2xl">
              {messages.map((msg) => (
                <div key={msg.id} className={cn("flex gap-3", msg.role === "user" ? "flex-row-reverse" : "flex-row")}>
                  {/* Avatar */}
                  <div
                    className={cn(
                      "w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5",
                      msg.role === "user" ? "bg-blue-600" : "bg-slate-700"
                    )}
                  >
                    {msg.role === "user" ? (
                      <User className="w-3.5 h-3.5 text-white" />
                    ) : (
                      <Bot className="w-3.5 h-3.5 text-white" />
                    )}
                  </div>
                  <div className={cn("max-w-lg", msg.role === "user" ? "items-end" : "items-start")} style={{ display: "flex", flexDirection: "column" }}>
                    <div
                      className={cn(
                        "px-4 py-3 rounded-2xl text-sm leading-relaxed",
                        msg.role === "user"
                          ? "bg-blue-600 text-white rounded-tr-sm"
                          : "bg-card border border-border text-foreground rounded-tl-sm"
                      )}
                      style={{ fontFamily: "'Inter', sans-serif" }}
                    >
                      {msg.role === "assistant"
                        ? msg.content.split("\n").map((line, li) => {
                            const bold = line.match(/^\*\*(.+?)\*\*\s*(.*)$/);
                            if (bold) {
                              return (
                                <div key={li} className={li > 0 ? "mt-1.5" : ""}>
                                  <span className="font-semibold text-foreground">{formatChemString(bold[1])}</span>{" "}
                                  <span>{formatChemString(bold[2])}</span>
                                </div>
                              );
                            }
                            return line ? <div key={li} className={li > 0 ? "mt-1" : ""}>{formatChemString(line)}</div> : null;
                          })
                        : msg.content}
                    </div>
                    <div className="flex items-center gap-2 mt-1 px-1">
                      <span className="text-xs text-muted-foreground" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
                        {formatTime(msg.created_at)}
                      </span>
                      {msg.metadata && (
                        <span className="text-xs text-blue-500 font-medium">· metadata attached</span>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </ScrollArea>

          {/* Input */}
          <div className="p-4 border-t border-border bg-card">
            <div className="flex gap-3 items-end">
              <div className="flex-1 relative">
                <textarea
                  className="w-full resize-none rounded-xl border border-border bg-background px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-400 transition-all"
                  style={{ fontFamily: "'Inter', sans-serif", minHeight: "44px", maxHeight: "120px" }}
                  placeholder="Ask for next best action, recommendations, or analysis…"
                  rows={1}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      handleSend();
                    }
                  }}
                />
              </div>
              <Button
                size="sm"
                className="h-10 px-4 gap-2"
                onClick={handleSend}
                disabled={!input.trim() || sending}
              >
                {sending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
                Send
              </Button>
            </div>
            <div className="flex items-center gap-3 mt-2 px-1">
              <span className="text-xs text-muted-foreground">Model:</span>
              <code className="text-xs text-muted-foreground" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
                {DEFAULT_MODEL.split("/").pop()}
              </code>
              <span className="text-xs text-muted-foreground">·</span>
              <span className="text-xs text-muted-foreground">Data:</span>
              <code className="text-xs text-muted-foreground" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
                {DEFAULT_DATASET.split("/").pop()}
              </code>
            </div>
          </div>
        </div>

        {/* Right: Metadata Viewer */}
        <div
          className="w-80 flex-shrink-0 border-l border-border flex flex-col"
          style={{ background: "oklch(0.99 0.002 240)" }}
        >
          <div className="px-4 py-3 border-b border-border">
            <div className="text-xs font-semibold text-foreground mb-2" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
              Response Metadata
            </div>
            <div className="flex gap-1">
              {(["recommendation", "reasoning", "literature", "trace"] as const).map((tab) => (
                <button
                  key={tab}
                  onClick={() => setMetaTab(tab)}
                  className={cn(
                    "px-2.5 py-1 rounded-md text-xs font-medium transition-colors capitalize",
                    metaTab === tab
                      ? "bg-blue-600 text-white"
                      : "text-muted-foreground hover:bg-muted"
                  )}
                >
                  {tab}
                </button>
              ))}
            </div>
          </div>

          <ScrollArea className="flex-1 p-4">
            {lastAssistantMsg?.metadata ? (
              <>
                {metaTab === "recommendation" && (
                  <div>
                    <div className="text-xs font-semibold text-muted-foreground mb-3 uppercase tracking-wide">
                      Ranked Candidates
                    </div>
                    <div className="space-y-3">
                      {rankedCandidates.length === 0 && (
                        <div className="text-xs text-muted-foreground">No recommendation payload in this message.</div>
                      )}
                      {rankedCandidates.map((cand, idx) => {
                        const rankRaw = cand.rank;
                        const rank = typeof rankRaw === "number" ? rankRaw : idx + 1;
                        const params = ((cand.params as AnyObj | undefined) ?? (cand.conditions as AnyObj | undefined) ?? {});
                        const pred = typeof cand.predicted_yield === "number" ? cand.predicted_yield : null;
                        const unc = typeof cand.predicted_uncertainty === "number" ? cand.predicted_uncertainty : null;
                        return (
                          <div key={idx} className="rounded-xl border border-border bg-muted/20 p-3">
                            <div className="flex items-start gap-2 mb-2">
                              <RankBadge rank={rank} />
                              <div className="flex-1">
                                <div className="flex items-center justify-between">
                                  <div className="text-xs font-semibold">Candidate #{rank}</div>
                                  <div className="text-xs font-mono" style={{ color: "oklch(0.52 0.22 260)" }}>
                                    {pred !== null ? `${pred.toFixed(2)}%` : "—"}
                                  </div>
                                </div>
                                <div className="mt-1">
                                  <ConfidenceBar uncertainty={unc} />
                                </div>
                              </div>
                            </div>
                            <div className="grid grid-cols-2 gap-1.5 mb-2">
                              {Object.entries(params).slice(0, 6).map(([k, v]) => (
                                <ValuePill key={k} label={k} value={v} />
                              ))}
                            </div>
                            <div className="text-[11px] text-muted-foreground">
                              {typeof cand.reasoning === "string" ? cand.reasoning : "Ranked by optimizer UCB score."}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
                {metaTab === "reasoning" && (
                  <div>
                    <div className="text-xs font-semibold text-muted-foreground mb-3 uppercase tracking-wide flex items-center gap-1.5">
                      <Brain className="w-3.5 h-3.5" />
                      Agent Reasoning
                    </div>
                    <div className="space-y-2 mb-3">
                      <ValuePill label="confidence" value={reasoning.confidence} />
                      <ValuePill label="why_now" value={reasoning.why_now} />
                      <ValuePill label="caution_note" value={reasoning.caution_note} />
                      <ValuePill label="decision_rule_after_result" value={reasoning.decision_rule_after_result} />
                    </div>
                    <div className="rounded-xl border border-border bg-muted/20 p-3">
                      <ReasoningText
                        text={[
                          `Why now: ${String(reasoning.why_now ?? "n/a")}`,
                          `Caution: ${String(reasoning.caution_note ?? "n/a")}`,
                          `Follow-up rule: ${String(reasoning.decision_rule_after_result ?? "n/a")}`,
                        ].join("\n\n")}
                      />
                    </div>
                  </div>
                )}
                {metaTab === "literature" && (
                  <div>
                    <div className="text-xs font-semibold text-muted-foreground mb-3 uppercase tracking-wide">
                      Literature Support
                    </div>
                    {Object.keys(literatureExplain).length > 0 && (
                      <div className="rounded-xl border border-border bg-muted/20 p-3 mb-3">
                        <div className="text-[11px] font-semibold mb-1">Summary</div>
                        <div className="text-[11px] text-muted-foreground mb-2">
                          {formatChemString(String(literatureExplain.paper_summary ?? "n/a"))}
                        </div>
                        <div className="text-[11px] font-semibold mb-1">Relevance</div>
                        <div className="text-[11px] text-muted-foreground mb-2">
                          {String(((literatureExplain.relevance as AnyObj | undefined)?.level ?? "n/a")).toUpperCase()}
                        </div>
                        <div className="text-[11px] font-semibold mb-1">Why related</div>
                        <div className="text-[11px] text-muted-foreground">
                          {(((literatureExplain.relevance as AnyObj | undefined)?.why_related as unknown[] | undefined) ?? [])
                            .slice(0, 2)
                            .map((x) => String(x))
                            .join(" · ") || "n/a"}
                        </div>
                      </div>
                    )}
                    <div className="space-y-2">
                      {((evidence.results as AnyObj[] | undefined) ?? []).slice(0, 5).map((item, idx) => (
                        <div key={idx} className="rounded-xl border border-border p-3 bg-muted/20">
                          <a
                            href={String(item.url ?? "#")}
                            target="_blank"
                            rel="noreferrer"
                            className="text-xs font-medium text-blue-600 hover:underline block"
                          >
                            {formatChemString(String(item.title ?? item.url ?? "Reference"))}
                          </a>
                          <div className="text-[11px] text-muted-foreground mt-1">
                            {formatChemString(String(item.snippet ?? "").slice(0, 220))}
                          </div>
                          <div className="flex items-center justify-between mt-2">
                            <div className="text-[10px] text-muted-foreground" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
                              DOI: {String(item.doi_hint ?? "n/a")}
                            </div>
                            <div className="text-[10px] text-muted-foreground font-mono">
                              score: {String(item.score ?? "n/a")}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                    {((evidence.results as unknown[] | undefined) ?? []).length === 0 && (
                      <div className="text-xs text-muted-foreground">No literature hits attached for this turn.</div>
                    )}
                  </div>
                )}
                {metaTab === "trace" && (
                  <div>
                    <div className="text-xs font-semibold text-muted-foreground mb-3 uppercase tracking-wide flex items-center gap-1.5">
                      <Cpu className="w-3.5 h-3.5" />
                      Agent Trace
                    </div>
                    <div className="rounded-xl border border-border bg-muted/20 p-3">
                      {(((meta as Record<string, unknown>)?.agent_trace as AnyObj[] | undefined) ?? []).length === 0 && (
                        <div className="text-xs text-muted-foreground">No tool trace for this message.</div>
                      )}
                      {(((meta as Record<string, unknown>)?.agent_trace as AnyObj[] | undefined) ?? []).map((step, idx) => (
                        <div key={idx} className="flex items-center gap-2 py-1.5 border-b last:border-0 border-border/60">
                          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 flex-shrink-0" />
                          <span className="text-xs flex-1">
                            {String(step.tool ?? `step_${idx + 1}`)}
                          </span>
                          <span className="text-[10px] text-muted-foreground font-mono">
                            {String(step.status ?? "ok")}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </>
            ) : (
              <div className="flex flex-col items-center justify-center h-40 text-center">
                <Layers className="w-8 h-8 text-muted-foreground/40 mb-2" />
                <div className="text-sm text-muted-foreground">No metadata yet</div>
                <div className="text-xs text-muted-foreground mt-1">Send a message to see recommendation data</div>
              </div>
            )}
          </ScrollArea>
        </div>
      </div>
    </AppLayout>
  );
}
