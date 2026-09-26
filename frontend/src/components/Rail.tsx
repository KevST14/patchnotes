import { ArrowRight, Brain } from "lucide-react";
import { api } from "../api";
import { useAsync, useHashRoute, useMeta } from "../hooks";
import type { Status } from "../types";
import { ago } from "../utils";
import { Sparkline } from "./Charts";

export function Rail({ status, catchupCount }: { status: Status | null; catchupCount: number | null }) {
  const { navigate } = useHashRoute();
  const { source } = useMeta();
  const trends = useAsync(() => api.trends("24h"), [status?.last_updated]);
  const now = Date.now() / 1000;

  return (
    <aside className="rail" aria-label="Sidebar">
      <section className="card rail-cta catchup-cta">
        <div className="mini-deck" aria-hidden>
          <i />
          <i />
          <i />
        </div>
        <h3>{catchupCount === null ? "Catch up" : catchupCount === 0 ? "You're all caught up" : `${catchupCount} to catch up on`}</h3>
        <p>
          {catchupCount === 0
            ? "Nothing new since your last skim. Check back later."
            : "Skim the last day and a half one card at a time. Keep or skip — your feed learns from it."}
        </p>
        <button type="button" className="btn btn-primary" onClick={() => navigate("catchup")} disabled={catchupCount === 0}>
          Start catch-up <ArrowRight size={15} aria-hidden />
        </button>
      </section>

      <section className="card">
        <h2 className="card-title">
          Rising now
          <button type="button" onClick={() => navigate("trends")}>
            All trends
          </button>
        </h2>
        {!trends.data && <p className="muted" style={{ margin: 0, fontSize: 13 }}>Reading the radar…</p>}
        {trends.data && trends.data.terms.length === 0 && (
          <p className="muted" style={{ margin: 0, fontSize: 13 }}>Nothing is spiking yet. Trends need a few stories from a few sources.</p>
        )}
        {trends.data?.terms.slice(0, 6).map((t) => (
          <button
            type="button"
            key={t.key}
            className="rising-row"
            onClick={() => navigate("trends", { term: t.key })}
            title={`${t.count} stories from ${t.sources.length} sources`}
          >
            <span className="label">{t.label}</span>
            <Sparkline values={t.spark} endTs={now} bucketSeconds={trends.data!.bucket_seconds} width={72} height={24} label={`${t.label} mentions`} />
            <span className="n">{t.ratio ? `×${t.ratio.toFixed(1)}` : "new"}</span>
          </button>
        ))}
      </section>

      <section className="card rail-cta">
        <h3>
          <Brain size={18} aria-hidden style={{ verticalAlign: -2, marginRight: 6, color: "var(--accent)" }} />
          This week's quiz
        </h3>
        <p>Eight questions built from the week's headlines. How much stuck?</p>
        <button type="button" className="btn" onClick={() => navigate("quiz")}>
          Take the quiz <ArrowRight size={15} aria-hidden />
        </button>
      </section>

      {status && (
        <section className="card">
          <h2 className="card-title">
            Sources
            <span className="mono" style={{ textTransform: "none", letterSpacing: 0 }}>
              {status.story_count.toLocaleString()} stories
            </span>
          </h2>
          <div className="health">
            {status.sources.map((s) => {
              const state = s.error ? "error" : s.last_success ? "ok" : "pending";
              const title = s.error
                ? `${s.name}: last attempt failed (${s.error})`
                : s.last_success
                  ? `${s.name}: updated ${ago(s.last_success)}`
                  : `${s.name}: waiting for first fetch`;
              return (
                <span key={s.id} className="health-item" data-state={state} title={title}>
                  <i aria-hidden />
                  <span>{source(s.id).short}</span>
                </span>
              );
            })}
          </div>
        </section>
      )}
    </aside>
  );
}
