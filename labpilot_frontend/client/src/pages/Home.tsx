// LabPilot Home / Workspace
// Design: Clinical Research Portal
// Hero with molecular network image, quick-access cards, recent activity

import { Link } from "wouter";
import { useEffect, useMemo, useState } from "react";
import AppLayout from "@/components/AppLayout";
import { apiGet, type ApiConversation, type ApiExperimentRun, type ApiTrainingRun } from "@/lib/api";
import {
  MessageSquare,
  BrainCircuit,
  Beaker,
  BarChart3,
  ArrowRight,
  TrendingUp,
  Clock,
  CheckCircle2,
  Loader2,
} from "lucide-react";

const HERO_IMG = "https://d2xsxph8kpxj0f.cloudfront.net/310519663435888256/LwQaGTexsoKSwC82giZxAm/labpilot-hero-eqZKDkk3LB6k99aYsEnTWt.webp";

function StatusDot({ status }: { status: string }) {
  if (status === "running") return <Loader2 className="w-3.5 h-3.5 text-blue-500 animate-spin" />;
  if (status === "completed") return <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />;
  return <Clock className="w-3.5 h-3.5 text-amber-500" />;
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export default function Home() {
  const [conversations, setConversations] = useState<ApiConversation[]>([]);
  const [trainingRuns, setTrainingRuns] = useState<ApiTrainingRun[]>([]);
  const [experimentRuns, setExperimentRuns] = useState<ApiExperimentRun[]>([]);

  useEffect(() => {
    let mounted = true;
    async function load() {
      try {
        const [conv, training, experiments] = await Promise.all([
          apiGet<ApiConversation[]>("/api/conversations"),
          apiGet<ApiTrainingRun[]>("/api/training/runs"),
          apiGet<ApiExperimentRun[]>("/api/experiments/runs"),
        ]);
        if (!mounted) return;
        setConversations(conv);
        setTrainingRuns(training);
        setExperimentRuns(experiments);
      } catch {
        if (!mounted) return;
        setConversations([]);
        setTrainingRuns([]);
        setExperimentRuns([]);
      }
    }
    load();
    return () => {
      mounted = false;
    };
  }, []);

  const recentConvs = useMemo(() => conversations.slice(0, 3), [conversations]);
  const recentTraining = useMemo(() => trainingRuns.slice(0, 3), [trainingRuns]);
  const recentExp = useMemo(() => experimentRuns.slice(0, 3), [experimentRuns]);

  return (
    <AppLayout>
      {/* Hero Banner */}
      <div className="relative h-52 overflow-hidden">
        <img
          src={HERO_IMG}
          alt="LabPilot molecular network"
          className="w-full h-full object-cover"
        />
        <div className="absolute inset-0" style={{ background: "linear-gradient(to right, oklch(0.175 0.04 255 / 0.85) 0%, oklch(0.175 0.04 255 / 0.4) 60%, transparent 100%)" }} />
        <div className="absolute inset-0 flex flex-col justify-center px-10">
          <div className="text-xs font-medium mb-2 tracking-widest" style={{ color: "oklch(0.72 0.18 260)", fontFamily: "'Inter', sans-serif" }}>
            SUZUKI-MIYAURA OPTIMIZATION
          </div>
          <h1 className="text-3xl font-bold text-white mb-1" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
            Welcome back, Researcher
          </h1>
          <p className="text-sm" style={{ color: "oklch(0.75 0.03 240)", fontFamily: "'Inter', sans-serif" }}>
            Your AI copilot is ready. {conversations.length} active conversations · {trainingRuns.filter((r) => r.status === "running").length} training run in progress
          </p>
        </div>
      </div>

      <div className="px-8 py-6 space-y-8">
        {/* Quick Access Cards */}
        <div>
          <h2 className="text-sm font-semibold text-muted-foreground mb-3 tracking-wide uppercase" style={{ fontFamily: "'Inter', sans-serif" }}>
            Quick Access
          </h2>
          <div className="grid grid-cols-4 gap-4">
            {[
              {
                href: "/conversations",
                icon: MessageSquare,
                label: "Conversations",
                desc: "Ask the AI copilot",
                count: conversations.length,
                color: "oklch(0.52 0.22 260)",
                bg: "oklch(0.52 0.22 260 / 0.08)",
              },
              {
                href: "/training",
                icon: BrainCircuit,
                label: "Model Training",
                desc: "Train surrogate models",
                count: trainingRuns.length,
                color: "oklch(0.72 0.18 160)",
                bg: "oklch(0.72 0.18 160 / 0.08)",
              },
              {
                href: "/experiments",
                icon: Beaker,
                label: "Experiments",
                desc: "Run simulations",
                count: experimentRuns.length,
                color: "oklch(0.75 0.18 80)",
                bg: "oklch(0.75 0.18 80 / 0.08)",
              },
              {
                href: "/evaluation",
                icon: BarChart3,
                label: "Evaluation",
                desc: "Benchmark results",
                count: 4,
                color: "oklch(0.62 0.20 300)",
                bg: "oklch(0.62 0.20 300 / 0.08)",
              },
            ].map(({ href, icon: Icon, label, desc, count, color, bg }) => (
              <Link key={href} href={href}>
                <div
                  className="labpilot-card p-5 hover:shadow-md transition-all duration-150 group cursor-pointer"
                  style={{ borderColor: `${color}30` }}
                >
                  <div
                    className="w-10 h-10 rounded-lg flex items-center justify-center mb-3"
                    style={{ background: bg }}
                  >
                    <Icon className="w-5 h-5" style={{ color }} />
                  </div>
                  <div className="text-base font-semibold text-foreground mb-0.5" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
                    {label}
                  </div>
                  <div className="text-xs text-muted-foreground mb-3">{desc}</div>
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-medium tabular-nums" style={{ color, fontFamily: "'JetBrains Mono', monospace" }}>
                      {count} records
                    </span>
                    <ArrowRight className="w-3.5 h-3.5 text-muted-foreground group-hover:translate-x-0.5 transition-transform" style={{ color }} />
                  </div>
                </div>
              </Link>
            ))}
          </div>
        </div>

        {/* Recent Activity — 3 columns */}
        <div className="grid grid-cols-3 gap-6">
          {/* Recent Conversations */}
          <div className="labpilot-card p-5">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold text-foreground text-sm" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
                Recent Conversations
              </h3>
              <Link href="/conversations">
                <span className="text-xs text-blue-600 hover:underline cursor-pointer">View all</span>
              </Link>
            </div>
            <div className="space-y-3">
              {recentConvs.map((c) => (
                <Link key={c.id} href={`/conversations/${c.id}`}>
                  <div className="flex items-start gap-3 p-2.5 rounded-lg hover:bg-muted/50 transition-colors cursor-pointer">
                    <div className="w-7 h-7 rounded-full bg-blue-100 flex items-center justify-center flex-shrink-0 mt-0.5">
                      <MessageSquare className="w-3.5 h-3.5 text-blue-600" />
                    </div>
                    <div className="min-w-0">
                      <div className="text-sm font-medium text-foreground truncate">{c.title}</div>
                      <div className="text-xs text-muted-foreground truncate mt-0.5">Conversation thread</div>
                      <div className="text-xs text-muted-foreground mt-1" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
                        {formatDate(c.updated_at)}
                      </div>
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          </div>

          {/* Recent Training Runs */}
          <div className="labpilot-card p-5">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold text-foreground text-sm" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
                Training Runs
              </h3>
              <Link href="/training">
                <span className="text-xs text-blue-600 hover:underline cursor-pointer">View all</span>
              </Link>
            </div>
            <div className="space-y-3">
              {recentTraining.map((r) => (
                <div key={r.id} className="flex items-center gap-3 p-2.5 rounded-lg hover:bg-muted/50 transition-colors">
                  <StatusDot status={r.status} />
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-medium text-foreground truncate">{r.model_path?.split("/").pop() ?? r.id}</div>
                    <div className="flex items-center gap-2 mt-0.5">
                      {typeof r.metrics?.r2 === "number" ? (
                        <>
                          <span className="text-xs text-muted-foreground" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
                            R²={r.metrics?.r2?.toFixed(3)}
                          </span>
                          <span className="text-xs text-muted-foreground" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
                            MAE={r.metrics?.mae?.toFixed(3)}
                          </span>
                        </>
                      ) : (
                        <span className="text-xs text-blue-500">Training in progress…</span>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Recent Experiments */}
          <div className="labpilot-card p-5">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold text-foreground text-sm" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
                Experiment Runs
              </h3>
              <Link href="/experiments">
                <span className="text-xs text-blue-600 hover:underline cursor-pointer">View all</span>
              </Link>
            </div>
            <div className="space-y-3">
              {recentExp.map((e) => (
                <div key={e.id} className="flex items-center gap-3 p-2.5 rounded-lg hover:bg-muted/50 transition-colors">
                  <div className="w-7 h-7 rounded-full bg-amber-50 flex items-center justify-center flex-shrink-0">
                    <TrendingUp className="w-3.5 h-3.5 text-amber-600" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-medium text-foreground truncate capitalize">{e.strategy}</div>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className="text-xs text-muted-foreground" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
                        Best: {e.summary?.best_yield?.toFixed(2) ?? "—"}%
                      </span>
                      <span className="text-xs text-muted-foreground">·</span>
                      <span className="text-xs text-muted-foreground">{e.summary?.steps_completed ?? 0} steps</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Key metrics strip */}
        <div className="labpilot-card p-5">
          <h3 className="font-semibold text-foreground text-sm mb-4" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
            Campaign Highlights
          </h3>
          <div className="grid grid-cols-5 gap-4 divide-x divide-border">
            {[
              { label: "Best Yield (LinUCB)", value: "94.2%", sub: "contextual_linucb", color: "oklch(0.52 0.22 260)" },
              { label: "Surrogate R²", value: "0.912", sub: "surrogate_suzuki_v3", color: "oklch(0.72 0.18 160)" },
              { label: "Surrogate MAE", value: "3.42", sub: "percentage points", color: "oklch(0.72 0.18 160)" },
              { label: "Threshold Hit Rate", value: "85%", sub: "LinUCB @ 20 steps", color: "oklch(0.75 0.18 80)" },
              { label: "Steps to Threshold", value: "7", sub: "LinUCB strategy", color: "oklch(0.62 0.20 300)" },
            ].map(({ label, value, sub, color }) => (
              <div key={label} className="px-4 first:pl-0">
                <div className="text-xs text-muted-foreground mb-1">{label}</div>
                <div
                  className="text-2xl font-medium tabular-nums"
                  style={{ fontFamily: "'JetBrains Mono', monospace", color }}
                >
                  {value}
                </div>
                <div className="text-xs text-muted-foreground mt-0.5">{sub}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </AppLayout>
  );
}
