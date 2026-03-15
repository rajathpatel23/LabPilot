export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://127.0.0.1:8010";

async function parseResponse<T>(res: Response): Promise<T> {
  const text = await res.text();
  if (!res.ok) {
    throw new Error(text || `Request failed (${res.status})`);
  }
  return (text ? JSON.parse(text) : {}) as T;
}

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`);
  return parseResponse<T>(res);
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return parseResponse<T>(res);
}

export type ApiConversation = {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
};

export type ApiMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
  metadata?: Record<string, unknown>;
};

export type ApiTrainingRun = {
  id: string;
  status: string;
  dataset_path: string;
  target_column: string;
  model_path?: string | null;
  metrics?: {
    r2?: number;
    mae?: number;
    train_size?: number;
    test_size?: number;
  };
  created_at: string;
};

export type ApiExperimentRun = {
  id: string;
  status: string;
  strategy: string;
  dataset_path: string;
  model_path: string;
  budget: number;
  n_init: number;
  seed: number;
  created_at: string;
  summary?: {
    best_yield?: number;
    steps_completed?: number;
    strategy?: string;
  };
  output_path?: string | null;
};

export type ApiSession = {
  id: string;
  title: string;
  conversation_id?: string | null;
  dataset_path: string;
  model_path: string;
  budget: number;
  top_k: number;
  status: string;
  steps_completed: number;
  best_observed_yield?: number | null;
  created_at: string;
  updated_at: string;
};
