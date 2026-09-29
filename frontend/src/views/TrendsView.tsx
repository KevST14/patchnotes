import { useEffect, useMemo } from "react";
import { toast } from "sonner";
import { BellOff, Info, Radar, Search } from "lucide-react";
import { api } from "../api";
import { Empty, Skeleton, SourceMark } from "../components/Bits";
import { SparkBars, Sparkline } from "../components/Charts";
import { useAsync, useHashRoute, useHotkeys, useMeta } from "../hooks";
import type { TrendTerm, TrendWindow, TrendsResponse } from "../types";
import { plural, timeAgo } from "../utils";

const WINDOW_LABEL: Record<TrendWindow, string> = { "24h": "Last 24 hours", "7d": "Last 7 days" };

function ratioText(t: TrendTerm) {
  if (t.is_new || t.ratio === null) return "new";
  return `×${t.ratio.toFixed(1)}`;
}

export function TrendsView({ lastUpdated }: { lastUpdated: number | null }) {
  const { params, replaceParams, navigate } = useHashRoute();
  const window_ = (params.get("w") === "7d" ? "7d" : "24h") as TrendWindow;
  const selectedKey = params.get("term");
  const { data, loading, error, reload } = useAsync(() => api.trends(window_), [window_, lastUpdated]);

  const terms = data?.terms ?? [];
  const selected = terms.find((t) => t.key === selectedKey) ?? terms[0];
  const index = selected ? terms.indexOf(selected) : -1;

  // Keep the URL pointing at what's shown, so a shared link opens the same term.
  useEffect(() => {
    if (data && selected && selected.key !== selectedKey) replaceParams({ term: selected.key });
  }, [data, selected, selectedKey, replaceParams]);

  useHotkeys({
    j: () => terms[index + 1] && replaceParams({ term: terms[index + 1].key }),
    k: () => terms[index - 1] && replaceParams({ term: terms[index - 1].key }),
    ArrowDown: () => terms[index + 1] && replaceParams({ term: terms[index + 1].key }),
    ArrowUp: () => terms[index - 1] && replaceParams({ term: terms[index - 1].key }),
  });

  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="page-title">Trend radar</h1>
          <p className="page-sub">Names and phrases turning up more than usual, across at least two different sources.</p>
        </div>
        <div className="seg" role="group" aria-label="Time window">
          {(["24h", "7d"] as TrendWindow[]).map((w) => (
            <button key={w} type="button" aria-pressed={window_ === w} onClick={() => replaceParams({ w, term: null })}>
              {WINDOW_LABEL[w]}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className="banner" data-tone="error">
          <span style={{ flex: 1 }}>{error}</span>
          <button className="btn" type="button" onClick={reload}>
            Retry
          </button>
        </div>
      )}
      {!data && loading && <Skeleton rows={4} />}

      {data && <BaselineNote data={data} />}

      {data && terms.length === 0 && (
        <Empty icon={<Radar size={22} />} title="Nothing's spiking">
          No name is turning up across enough sources more than usual right now. Try the 7-day window.
        </Empty>
      )}

      {data && terms.length > 0 && (
        <div className="trends feed" data-loading={loading}>
          <div>
            <table className="rising-table">
              <thead>
                <tr>
                  <th className="hide-sm">#</th>
                  <th>Term</th>
                  <th>{window_ === "24h" ? "Last 7 days" : "Last 4 weeks"}</th>
                  <th className="num">Stories</th>
                  <th className="num" title="Stories in this window compared with its usual rate">vs usual</th>
                </tr>
              </thead>
              <tbody>
                {terms.map((t, i) => (
                  <tr
                    key={t.key}
                    data-selected={t.key === selected?.key}
                    onClick={() => replaceParams({ term: t.key })}
                    tabIndex={0}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        replaceParams({ term: t.key });
                      }
                    }}
                    aria-selected={t.key === selected?.key}
                  >
                    <td className="rank hide-sm">{i + 1}</td>
                    <td>
                      <div className="term-label">{t.label}</div>
                      <div className="term-sources">{plural(t.sources.length, "source")}</div>
                    </td>
                    <td>
                      <Sparkline values={t.spark} endTs={data.generated_at} bucketSeconds={data.bucket_seconds} label={`${t.label} stories over time`} />
                    </td>
                    <td className="num">{t.count}</td>
                    <td className="num">
                      <span className="ratio" data-new={t.is_new || t.ratio === null}>
                        {ratioText(t)}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {selected && (
            <TermDetail
              term={selected}
              data={data}
              window_={window_}
              onSearch={() => navigate("today", { q: selected.label })}
            />
          )}
        </div>
      )}

      {data && (
        <section style={{ marginTop: 44 }}>
          <h2 className="section-title">Topics · {WINDOW_LABEL[window_].toLowerCase()}</h2>
          <div className="multiples">
            {data.topics.map((t) => (
              <button type="button" key={t.id} className="multiple" onClick={() => navigate("today", { topic: t.id, view: "latest" })}>
                <div className="multiple-head">
                  <span className="name">{t.label}</span>
                  <span className="delta">
                    {t.change === null ? (
                      <>{Math.round(t.share * 100)}% of stories</>
                    ) : (
                      <>
                        <b>
                          {t.change >= 0 ? "▲" : "▼"} {Math.abs(Math.round(t.change * 100))}%
                        </b>{" "}
                        vs usual
                      </>
                    )}
                  </span>
                </div>
                <div className="multiple-value">{t.count}</div>
                <SparkBars values={t.spark} endTs={data.generated_at} bucketSeconds={data.bucket_seconds} label={`${t.label} stories over time`} height={40} />
              </button>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function BaselineNote({ data }: { data: TrendsResponse }) {
  const { meta } = useMeta();
  const missing = meta.sources.length - data.baseline_sources.length - 1; // GitHub never counts
  if (data.has_baseline && missing <= 0) return null;
  return (
    <p className="note" style={{ margin: "0 0 18px" }}>
      <Info size={14} aria-hidden />
      {data.has_baseline
        ? `Still building history for ${plural(missing, "source")}, so their stories aren't compared against a "usual" yet. This evens out after a day or two of running.`
        : `Patch Notes hasn't been running long enough to know what's usual, so everything below is ranked on volume and spread for now.`}
    </p>
  );
}

function TermDetail({
  term,
  data,
  window_,
  onSearch,
}: {
  term: TrendTerm;
  data: TrendsResponse;
  window_: TrendWindow;
  onSearch: () => void;
}) {
  const { source } = useMeta();
  const lede = useMemo(() => {
    const base = `${plural(term.count, "story", "stories")} from ${term.sources.map((s) => source(s).short).join(", ")} in the ${WINDOW_LABEL[window_].toLowerCase()}`;
    if (term.is_new || term.ratio === null) return `${base} — barely mentioned before that.`;
    return `${base} — ${term.ratio.toFixed(1)}× its usual rate.`;
  }, [term, window_, source]);

  const mute = async () => {
    try {
      const prefs = await api.prefs();
      await api.setPrefs({ muted_terms: [...prefs.muted_terms, term.label] });
      toast.success(`Muted “${term.label}”`, {
        description: "Stories mentioning it won't show in your feed. Unmute in Settings.",
      });
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  return (
    <aside className="term-detail card" aria-live="polite">
      <h2>{term.label}</h2>
      <p className="lede">{lede}</p>
      <SparkBars values={term.spark} endTs={data.generated_at} bucketSeconds={data.bucket_seconds} label={`${term.label} stories over time`} height={64} />
      <div style={{ display: "flex", gap: 8, margin: "16px 0 6px", flexWrap: "wrap" }}>
        <button type="button" className="btn btn-primary" onClick={onSearch}>
          <Search size={15} aria-hidden /> Every story about it
        </button>
        <button type="button" className="btn btn-ghost" onClick={mute} title="Hide stories mentioning this from your feed">
          <BellOff size={15} aria-hidden /> Mute
        </button>
      </div>
      <div style={{ marginTop: 10 }}>
        {term.stories.map((s) => (
          <a
            key={s.id}
            className="mini-story"
            href={s.url}
            target="_blank"
            rel="noreferrer"
            onClick={() => api.interact(s.id, "open").catch(() => undefined)}
          >
            <div className="t">{s.title}</div>
            <div className="m">
              <SourceMark id={s.source} />
              <span>{timeAgo(s.published_at)}</span>
            </div>
          </a>
        ))}
      </div>
    </aside>
  );
}
