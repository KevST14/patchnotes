export type SourceKind = "hn" | "lobsters" | "github" | "rss";

export interface Source {
  id: string;
  name: string;
  short: string;
  kind: SourceKind;
  homepage: string;
  color: string;
}

export interface Topic {
  id: string;
  label: string;
}

export interface Meta {
  sources: Source[];
  topics: Topic[];
  trend_windows: TrendWindow[];
}

export interface Story {
  id: string;
  source: string;
  title: string;
  url: string;
  discussion_url: string | null;
  summary: string;
  image: string | null;
  author: string | null;
  published_at: number;
  score: number | null;
  comments: number | null;
  topics: string[];
  extra: { repo?: string; language?: string | null; forks?: number };
  saved: boolean;
  read: boolean;
  triage: "keep" | "skip" | null;
  saved_at?: number;
}

export interface DiscussionRef {
  story_id: string;
  source: string;
  url: string;
  score: number | null;
  comments: number | null;
}

export interface Cluster {
  id: string;
  lead: Story;
  coverage: Story[];
  sources: string[];
  source_count: number;
  topics: string[];
  first_published: number;
  last_published: number;
  discussions: DiscussionRef[];
  reasons: string[];
  score: number;
}

export type FeedView = "foryou" | "top" | "latest";

export interface FeedResponse {
  view: FeedView;
  total: number;
  offset: number;
  has_more: boolean;
  items: Cluster[];
  personalised: boolean;
}

export interface CatchupResponse {
  remaining: number;
  reviewed: number;
  items: Cluster[];
}

export interface Comment {
  author: string;
  paragraphs: string[];
  replies: number;
  url: string;
  score?: number | null;
  created_at?: number | null;
}

export interface Discussion {
  story_id: string;
  source: string;
  url: string;
  total: number | null;
  comments: Comment[];
}

export interface ProfileRow {
  id: string;
  label: string;
  affinity: number;
  signals: number;
}

export interface Profile {
  signals: number;
  topics: ProfileRow[];
  sources: ProfileRow[];
  liked_terms: ProfileRow[];
  disliked_terms: ProfileRow[];
  followed_topics: string[];
}

export interface Prefs {
  followed_topics: string[];
  muted_terms: string[];
  muted_sources: string[];
}

export type TrendWindow = "24h" | "7d";

export interface TrendTerm {
  key: string;
  label: string;
  count: number;
  sources: string[];
  clusters: number;
  expected: number;
  ratio: number | null;
  is_new: boolean;
  score: number;
  spark: number[];
  stories: Story[];
}

export interface TopicVolume {
  id: string;
  label: string;
  count: number;
  share: number;
  expected: number | null;
  change: number | null;
  spark: number[];
}

export interface TrendsResponse {
  window: TrendWindow;
  has_baseline: boolean;
  baseline_sources: string[];
  bucket_seconds: number;
  terms: TrendTerm[];
  topics: TopicVolume[];
  generated_at: number;
}

export interface StoryRef {
  id: string;
  title: string;
  url: string;
  source: string;
  published_at: number;
}

export interface QuizQuestion {
  id: string;
  type: "blank" | "outlet" | "hn" | "coverage";
  prompt: string;
  headline: string | null;
  options: string[];
  option_values?: string[];
  answer: number;
  explanation: string;
  story: StoryRef;
  seen: boolean;
}

export interface Quiz {
  id: string;
  round: number;
  questions: QuizQuestion[];
  pool_size: number;
}

export interface QuizResult {
  id: number;
  quiz_id: string;
  score: number;
  total: number;
  taken_at: number;
}

export interface SourceStatus {
  id: string;
  name: string;
  last_success: number | null;
  last_attempt: number | null;
  error: string | null;
  items: number | null;
}

export interface Status {
  fetching: boolean;
  last_run: { started: number | null; finished: number | null; new: number };
  last_updated: number | null;
  story_count: number;
  interval_seconds: number;
  sources: SourceStatus[];
}

export type Action = "keep" | "skip" | "open" | "save" | "hide";
