import { forwardRef, useEffect, useRef, useState } from "react";
import { ArrowUp, Bookmark, BookmarkCheck, ExternalLink, EyeOff, MessageSquare, Sparkles, Star } from "lucide-react";
import { api } from "../api";
import { useMeta } from "../hooks";
import type { Cluster, Discussion, Story } from "../types";
import { compact, domainOf, fullDate, timeAgo } from "../utils";
import { SourceMark, SourceStack, TopicTag } from "./Bits";

export type Panel = "coverage" | "comments" | null;

interface Props {
  cluster: Cluster;
  focused: boolean;
  panel: Panel;
  onPanel: (panel: Panel) => void;
  onOpen: (story: Story) => void;
  onToggleSave: (story: Story) => void;
  onHide: (cluster: Cluster) => void;
  onTopic: (topicId: string) => void;
  onFocus: () => void;
  showReasons?: boolean;
  /** Published since your last visit. */
  isNew?: boolean;
}

export const StoryCard = forwardRef<HTMLElement, Props>(function StoryCard(
  { cluster, focused, panel, onPanel, onOpen, onToggleSave, onHide, onTopic, onFocus, showReasons, isNew },
  ref,
) {
  const { source } = useMeta();
  const lead = cluster.lead;
  const [imgOk, setImgOk] = useState(true);
  const [imgLoaded, setImgLoaded] = useState(false);
  // Pop the bookmark only on the transition to saved, not on first render.
  const [pop, setPop] = useState(false);
  const wasSaved = useRef(lead.saved);
  useEffect(() => {
    if (lead.saved && !wasSaved.current) {
      setPop(true);
      const id = window.setTimeout(() => setPop(false), 320);
      wasSaved.current = lead.saved;
      return () => window.clearTimeout(id);
    }
    wasSaved.current = lead.saved;
  }, [lead.saved]);
  const kind = source(lead.source).kind;
  const linkDomain = kind !== "rss" ? domainOf(lead.url) : "";
  const hn = cluster.discussions.find((d) => d.source === "hn");
  const lob = cluster.discussions.find((d) => d.source === "lobsters");
  const thread = hn ?? lob;
  const showThumb = Boolean(lead.image && imgOk);

  return (
    <article
      ref={ref}
      className="story"
      data-focused={focused}
      data-read={lead.read}
      onPointerDown={onFocus}
      aria-label={lead.title}
    >
      <div className="story-grid" data-thumb={showThumb}>
        <div>
          <div className="story-top">
            {isNew && !lead.read && <span className="new-badge">new</span>}
            <SourceMark id={lead.source} />
            <span className="dot">·</span>
            <time dateTime={new Date(lead.published_at * 1000).toISOString()} title={fullDate(lead.published_at)} className="mono">
              {timeAgo(lead.published_at)}
            </time>
            {linkDomain && (
              <>
                <span className="dot">·</span>
                <span className="mono">{linkDomain}</span>
              </>
            )}
            {cluster.topics.slice(0, 2).map((t) => (
              <TopicTag key={t} id={t} onClick={onTopic} />
            ))}
          </div>
          <h2 className="story-title">
            <a href={lead.url} target="_blank" rel="noreferrer" onClick={() => onOpen(lead)}>
              {lead.title}
            </a>
          </h2>
          {lead.summary && <p className="story-summary">{lead.summary}</p>}
        </div>
        {showThumb && (
          <div className="thumb-wrap">
            <img
              src={lead.image!}
              alt=""
              loading="lazy"
              referrerPolicy="no-referrer"
              data-loaded={imgLoaded}
              onLoad={() => setImgLoaded(true)}
              onError={() => setImgOk(false)}
            />
          </div>
        )}
      </div>

      {showReasons && cluster.reasons.length > 0 && (
        <div className="reasons">
          {cluster.reasons.slice(0, 2).map((r) => (
            <span className="reason" key={r}>
              <Sparkles size={12} aria-hidden />
              {r}
            </span>
          ))}
        </div>
      )}

      <div className="story-meta">
        {cluster.source_count > 1 && (
          <button
            type="button"
            className="meta-btn coverage-pill"
            aria-expanded={panel === "coverage"}
            onClick={() => onPanel(panel === "coverage" ? null : "coverage")}
            title="Compare how each outlet covered it (e)"
          >
            <SourceStack ids={cluster.sources} />
            {cluster.source_count} sources
          </button>
        )}
        {thread && (
          <button
            type="button"
            className="meta-btn"
            aria-expanded={panel === "comments"}
            onClick={() => onPanel(panel === "comments" ? null : "comments")}
            title="Read the top comments (c)"
          >
            {thread.score != null && (
              <span className="meta-item">
                <ArrowUp size={13} aria-hidden />
                {compact(thread.score)}
              </span>
            )}
            <span className="meta-item">
              <MessageSquare size={13} aria-hidden />
              {compact(thread.comments ?? 0)}
            </span>
          </button>
        )}
        {kind === "github" && lead.score != null && (
          <span className="meta-item" title="GitHub stars">
            <Star size={13} aria-hidden />
            {compact(lead.score)}
            {lead.extra.language && <span>· {lead.extra.language}</span>}
          </span>
        )}
        <div className="story-actions">
          <button
            type="button"
            className="icon-btn"
            aria-pressed={lead.saved}
            data-pop={pop}
            aria-label={lead.saved ? "Remove from saved" : "Save for later"}
            title={lead.saved ? "Saved (s)" : "Save for later (s)"}
            onClick={() => onToggleSave(lead)}
          >
            {lead.saved ? <BookmarkCheck size={17} /> : <Bookmark size={17} />}
          </button>
          <button type="button" className="icon-btn" aria-label="Not interested" title="Not interested (x)" onClick={() => onHide(cluster)}>
            <EyeOff size={17} />
          </button>
          <a className="icon-btn" href={lead.url} target="_blank" rel="noreferrer" aria-label="Open story" title="Open (o)" onClick={() => onOpen(lead)}>
            <ExternalLink size={17} />
          </a>
        </div>
      </div>

      {cluster.source_count > 1 && (
        <div className="expand" data-open={panel === "coverage"} aria-hidden={panel !== "coverage"}>
          <div>{panel === "coverage" && <CoveragePanel cluster={cluster} onOpen={onOpen} />}</div>
        </div>
      )}
      {thread && (
        <div className="expand" data-open={panel === "comments"} aria-hidden={panel !== "comments"}>
          <div>{panel === "comments" && <CommentsPanel cluster={cluster} />}</div>
        </div>
      )}
    </article>
  );
});

function CoveragePanel({ cluster, onOpen }: { cluster: Cluster; onOpen: (s: Story) => void }) {
  const all = [cluster.lead, ...cluster.coverage].sort((a, b) => a.published_at - b.published_at);
  const first = all[0];
  const spanHours = (all[all.length - 1].published_at - first.published_at) / 3600;
  return (
    <div className="panel">
      <div className="panel-head">
        <span>How {all.length} outlets told it</span>
        <span>{spanHours >= 1 ? `over ${Math.round(spanHours)}h` : "within the hour"}</span>
      </div>
      {all.map((s) => (
        <a key={s.id} className="coverage-row" href={s.url} target="_blank" rel="noreferrer" onClick={() => onOpen(s)}>
          <SourceMark id={s.source} />
          <span className="headline">{s.title}</span>
          <span className="when">
            {timeAgo(s.published_at)}
            {s.id === first.id && <span className="first-badge">first</span>}
          </span>
        </a>
      ))}
    </div>
  );
}

function CommentsPanel({ cluster }: { cluster: Cluster }) {
  const threads = [...cluster.discussions].sort((a, b) => Number(b.source === "hn") - Number(a.source === "hn"));
  const [active, setActive] = useState(threads[0]);
  const [data, setData] = useState<Discussion | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setData(null);
    setError(null);
    api
      .discussion(active.story_id)
      .then((d) => !cancelled && setData(d))
      .catch((e: Error) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [active.story_id]);

  return (
    <div className="panel">
      <div className="panel-head">
        <span>Top comments</span>
        {threads.length > 1 && (
          <span className="seg" style={{ padding: 2 }}>
            {threads.map((t) => (
              <button key={t.story_id} type="button" aria-pressed={t.story_id === active.story_id} onClick={() => setActive(t)}>
                {t.source === "hn" ? "HN" : "Lobsters"}
              </button>
            ))}
          </span>
        )}
      </div>
      {error && <div className="comment">Couldn't load the thread: {error}</div>}
      {!data && !error && <div className="comment muted">Loading the thread…</div>}
      {data && data.comments.length === 0 && <div className="comment muted">No comments yet.</div>}
      {data?.comments.map((c) => (
        <div className="comment" key={c.url}>
          <div className="comment-head">
            <b>{c.author}</b>
            {c.score != null && <span>{c.score} pts</span>}
            {c.replies > 0 && <span>{c.replies} {c.replies === 1 ? "reply" : "replies"}</span>}
          </div>
          {c.paragraphs.slice(0, 4).map((p, i) => (
            <p key={i}>{p}</p>
          ))}
        </div>
      ))}
      <div className="panel-foot">
        <a href={active.url} target="_blank" rel="noreferrer">
          Read all {active.comments ?? ""} comments on {active.source === "hn" ? "Hacker News" : "Lobsters"}
          <ExternalLink size={13} aria-hidden />
        </a>
      </div>
    </div>
  );
}
