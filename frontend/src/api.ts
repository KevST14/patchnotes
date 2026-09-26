import type {
  Action,
  CatchupResponse,
  Cluster,
  Discussion,
  FeedResponse,
  FeedView,
  Meta,
  Prefs,
  Profile,
  Quiz,
  QuizResult,
  Status,
  Story,
  TrendWindow,
  TrendsResponse,
} from "./types";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let resp: Response;
  try {
    resp = await fetch(`/api${path}`, {
      ...init,
      headers: init?.body ? { "Content-Type": "application/json", ...init.headers } : init?.headers,
    });
  } catch {
    throw new ApiError(0, "Can't reach the Patch Notes backend. Is it running on :8000?");
  }
  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      detail = (await resp.json()).detail ?? detail;
    } catch {
      /* not JSON */
    }
    throw new ApiError(resp.status, detail);
  }
  return resp.json() as Promise<T>;
}

function qs(params: Record<string, string | number | undefined | null>): string {
  const search = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") search.set(k, String(v));
  }
  const s = search.toString();
  return s ? `?${s}` : "";
}

export const api = {
  meta: () => request<Meta>("/meta"),
  status: () => request<Status>("/status"),
  refresh: () => request<{ status: string }>("/refresh", { method: "POST" }),

  feed: (p: { view: FeedView; topic?: string | null; source?: string | null; q?: string; limit?: number; offset?: number }) =>
    request<FeedResponse>(`/feed${qs(p)}`),
  cluster: (id: string) => request<Cluster>(`/clusters/${id}`),
  discussion: (storyId: string) => request<Discussion>(`/stories/${storyId}/discussion`),

  interact: (storyId: string, action: Action) =>
    request<{ status: string }>("/interactions", { method: "POST", body: JSON.stringify({ story_id: storyId, action }) }),
  undo: (storyId: string) => request<{ undone: string }>(`/interactions/${storyId}/undo`, { method: "POST" }),

  saved: () => request<Story[]>("/saved"),
  save: (storyId: string) => request<{ status: string }>(`/saved/${storyId}`, { method: "PUT" }),
  unsave: (storyId: string) => request<{ status: string }>(`/saved/${storyId}`, { method: "DELETE" }),

  catchup: (limit = 30) => request<CatchupResponse>(`/catchup${qs({ limit })}`),
  profile: () => request<Profile>("/profile"),
  prefs: () => request<Prefs>("/prefs"),
  setPrefs: (prefs: Partial<Prefs>) => request<Prefs>("/prefs", { method: "PUT", body: JSON.stringify(prefs) }),

  trends: (window: TrendWindow) => request<TrendsResponse>(`/trends${qs({ window })}`),

  quiz: (round = 1) => request<Quiz>(`/quiz${qs({ round })}`),
  quizResults: () => request<QuizResult[]>("/quiz/results"),
  addQuizResult: (quizId: string, score: number, total: number) =>
    request<QuizResult>("/quiz/results", { method: "POST", body: JSON.stringify({ quiz_id: quizId, score, total }) }),
};
