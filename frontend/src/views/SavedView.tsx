import { useMemo, useState } from "react";
import { toast } from "sonner";
import { Bookmark, BookmarkX, Copy, ExternalLink, Search } from "lucide-react";
import { api } from "../api";
import { Empty, Skeleton, SourceMark, TopicTag } from "../components/Bits";
import { useAsync, useHashRoute } from "../hooks";
import type { Story } from "../types";
import { ago } from "../utils";

export function SavedView() {
  const { navigate } = useHashRoute();
  const { data, setData, loading, error } = useAsync(() => api.saved(), []);
  const [filter, setFilter] = useState("");
  const [leaving, setLeaving] = useState<Set<string>>(() => new Set());

  const shown = useMemo(() => {
    const words = filter.toLowerCase().split(/\s+/).filter(Boolean);
    return (data ?? []).filter((s) => words.every((w) => `${s.title} ${s.summary}`.toLowerCase().includes(w)));
  }, [data, filter]);

  const remove = async (story: Story) => {
    setLeaving((prev) => new Set(prev).add(story.id));
    window.setTimeout(() => {
      setData((prev) => (prev ?? []).filter((s) => s.id !== story.id));
      setLeaving((prev) => {
        const next = new Set(prev);
        next.delete(story.id);
        return next;
      });
    }, 230);
    try {
      await api.unsave(story.id);
      toast("Removed from saved", {
        action: {
          label: "Undo",
          onClick: async () => {
            await api.save(story.id);
            setData((prev) => [{ ...story, saved: true }, ...(prev ?? [])].sort((a, b) => (b.saved_at ?? 0) - (a.saved_at ?? 0)));
          },
        },
      });
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  const copyMarkdown = async () => {
    const md = shown.map((s) => `- [${s.title}](${s.url})`).join("\n");
    try {
      await navigator.clipboard.writeText(md);
      toast.success(`Copied ${shown.length} links as Markdown`);
    } catch {
      toast.error("Couldn't reach the clipboard");
    }
  };

  return (
    <div className="saved-list">
      <div className="page-head">
        <div>
          <h1 className="page-title">Saved</h1>
          <p className="page-sub">Stories you put aside for later. They're kept even after the rest of the feed ages out.</p>
        </div>
        {shown.length > 0 && (
          <button type="button" className="btn" onClick={copyMarkdown}>
            <Copy size={15} aria-hidden /> Copy as Markdown
          </button>
        )}
      </div>

      {error && <div className="banner" data-tone="error">{error}</div>}
      {!data && loading && <Skeleton rows={3} />}

      {data && data.length === 0 && (
        <Empty
          icon={<Bookmark size={22} />}
          title="Nothing saved yet"
          action={
            <button type="button" className="btn" onClick={() => navigate("today")}>
              Browse today's stories
            </button>
          }
        >
          Press <kbd>s</kbd> on any story, or swipe a card up in catch-up mode, to keep it here.
        </Empty>
      )}

      {data && data.length > 0 && (
        <>
          <label className="search" style={{ maxWidth: 420, marginBottom: 6 }}>
            <Search size={15} aria-hidden />
            <span className="sr-only">Filter saved stories</span>
            <input type="search" placeholder={`Filter ${data.length} saved stories…`} value={filter} onChange={(e) => setFilter(e.target.value)} />
          </label>
          <div className="feed">
            {shown.map((s) => (
              <div className="story-slot" key={s.id} data-leaving={leaving.has(s.id)}>
                <article className="story" data-read={s.read}>
                  <div className="story-top">
                    <SourceMark id={s.source} />
                    <span className="dot">·</span>
                    <span className="mono">published {ago(s.published_at)}</span>
                    {s.saved_at && (
                      <>
                        <span className="dot">·</span>
                        <span className="mono">saved {ago(s.saved_at)}</span>
                      </>
                    )}
                    {s.topics.slice(0, 2).map((t) => (
                      <TopicTag key={t} id={t} onClick={(id) => navigate("today", { topic: id })} />
                    ))}
                  </div>
                  <h2 className="story-title">
                    <a href={s.url} target="_blank" rel="noreferrer" onClick={() => api.interact(s.id, "open").catch(() => undefined)}>
                      {s.title}
                    </a>
                  </h2>
                  {s.summary && <p className="story-summary">{s.summary}</p>}
                  <div className="story-meta">
                    <div className="story-actions">
                      <button type="button" className="icon-btn" aria-label="Remove from saved" title="Remove from saved" onClick={() => remove(s)}>
                        <BookmarkX size={17} />
                      </button>
                      <a className="icon-btn" href={s.url} target="_blank" rel="noreferrer" aria-label="Open story">
                        <ExternalLink size={17} />
                      </a>
                    </div>
                  </div>
                </article>
              </div>
            ))}
            {shown.length === 0 && <p className="muted">Nothing saved matches “{filter}”.</p>}
          </div>
        </>
      )}
    </div>
  );
}
