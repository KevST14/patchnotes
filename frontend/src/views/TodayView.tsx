import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { ArrowUp, Clock, Flame, Inbox, RefreshCw, Search, Sparkles, X } from "lucide-react";
import { api } from "../api";
import { Empty, Skeleton } from "../components/Bits";
import { Rail } from "../components/Rail";
import { StoryCard, type Panel } from "../components/StoryCard";
import { useHashRoute, useHotkeys, useLastVisit, useMeta, useReducedMotion, useScrolledPast } from "../hooks";
import type { Cluster, FeedResponse, FeedView, Status, Story } from "../types";
import { ago, dayLabel, plural, timeAgoLong } from "../utils";

const PAGE = 30;

const VIEWS: { id: FeedView; label: string; icon: typeof Sparkles; hint: string }[] = [
  { id: "foryou", label: "For you", icon: Sparkles, hint: "Ranked by what you keep, save and read" },
  { id: "top", label: "Top", icon: Flame, hint: "Biggest stories right now, across every source" },
  { id: "latest", label: "Latest", icon: Clock, hint: "Newest first" },
];

interface Props {
  status: Status | null;
  catchupCount: number | null;
  onCatchupChanged: () => void;
}

export function TodayView({ status, catchupCount, onCatchupChanged }: Props) {
  const { meta } = useMeta();
  const { params, replaceParams, navigate } = useHashRoute();
  const view = (["foryou", "top", "latest"].includes(params.get("view") ?? "") ? params.get("view") : "foryou") as FeedView;
  const topic = params.get("topic");
  const source = params.get("source");
  const q = params.get("q") ?? "";

  const [query, setQuery] = useState(q);
  const [feed, setFeed] = useState<FeedResponse | null>(null);
  const [items, setItems] = useState<Cluster[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [focus, setFocus] = useState(-1);
  const [panels, setPanels] = useState<Record<string, Panel>>({});
  const [loadedAt, setLoadedAt] = useState<number | null>(null);
  const [leaving, setLeaving] = useState<Set<string>>(() => new Set());
  const [entering, setEntering] = useState(false);
  const lastVisit = useLastVisit();
  const reduceMotion = useReducedMotion();
  const scrolled = useScrolledPast(900);
  const searchRef = useRef<HTMLInputElement>(null);
  const cardRefs = useRef<(HTMLElement | null)[]>([]);
  const seq = useRef(0);

  // Debounce typing into the URL (which drives the fetch).
  useEffect(() => {
    const id = window.setTimeout(() => {
      if (query.trim() !== q) replaceParams({ q: query.trim() || null });
    }, 250);
    return () => window.clearTimeout(id);
  }, [query, q, replaceParams]);

  const load = useCallback(
    async (offset = 0) => {
      const id = ++seq.current;
      setLoading(true);
      try {
        const res = await api.feed({ view, topic, source, q: q || undefined, limit: PAGE, offset });
        if (id !== seq.current) return;
        setFeed(res);
        setItems((prev) => (offset === 0 ? res.items : [...prev, ...res.items]));
        setError(null);
        if (offset === 0) {
          setFocus(-1);
          setPanels({});
          setLoadedAt(Date.now() / 1000);
          setEntering(true);
          setHasNewer(false);
        }
      } catch (e) {
        if (id === seq.current) setError((e as Error).message);
      } finally {
        if (id === seq.current) setLoading(false);
      }
    },
    [view, topic, source, q],
  );

  useEffect(() => {
    load(0);
  }, [load]);

  // The entrance stagger plays once per load, then gets out of the way.
  useEffect(() => {
    if (!entering) return;
    const id = window.setTimeout(() => setEntering(false), 8 * 40 + 340);
    return () => window.clearTimeout(id);
  }, [entering]);

  // When a background fetch brings in new stories, don't reshuffle the list
  // under the reader — offer a button instead. (On an empty first load, just
  // show them.)
  const [hasNewer, setHasNewer] = useState(false);
  const finished = status?.last_run.finished ?? null;
  const newCount = status?.last_run.new ?? 0;
  useEffect(() => {
    if (finished && loadedAt && finished > loadedAt && newCount > 0) setHasNewer(true);
  }, [finished, newCount, loadedAt]);
  useEffect(() => {
    if (items.length === 0 && finished && loadedAt && finished > loadedAt) load(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [finished]);

  const patchStory = useCallback((storyId: string, patch: Partial<Story>) => {
    setItems((prev) =>
      prev.map((c) => ({
        ...c,
        lead: c.lead.id === storyId ? { ...c.lead, ...patch } : c.lead,
        coverage: c.coverage.map((s) => (s.id === storyId ? { ...s, ...patch } : s)),
      })),
    );
  }, []);

  const onOpen = useCallback(
    (story: Story) => {
      patchStory(story.id, { read: true });
      api.interact(story.id, "open").catch(() => undefined);
    },
    [patchStory],
  );

  const onToggleSave = useCallback(
    async (story: Story) => {
      const next = !story.saved;
      patchStory(story.id, { saved: next });
      try {
        if (next) {
          await api.save(story.id);
          toast.success("Saved for later", {
            action: { label: "View saved", onClick: () => navigate("saved") },
          });
        } else {
          await api.unsave(story.id);
          toast("Removed from saved");
        }
        onCatchupChanged();
      } catch (e) {
        patchStory(story.id, { saved: !next });
        toast.error((e as Error).message);
      }
    },
    [patchStory, navigate, onCatchupChanged],
  );

  const onHide = useCallback(
    async (cluster: Cluster) => {
      const index = items.findIndex((c) => c.id === cluster.id);
      // Collapse the card first, then drop it from the list.
      setLeaving((prev) => new Set(prev).add(cluster.id));
      window.setTimeout(() => {
        setItems((prev) => prev.filter((c) => c.id !== cluster.id));
        setLeaving((prev) => {
          const next = new Set(prev);
          next.delete(cluster.id);
          return next;
        });
      }, 230);
      try {
        await api.interact(cluster.lead.id, "hide");
        onCatchupChanged();
        toast("Hidden — you'll see fewer stories like this", {
          action: {
            label: "Undo",
            onClick: async () => {
              await api.undo(cluster.lead.id);
              setItems((prev) => {
                const copy = [...prev];
                copy.splice(Math.min(index, copy.length), 0, cluster);
                return copy;
              });
              onCatchupChanged();
            },
          },
        });
      } catch (e) {
        toast.error((e as Error).message);
        load(0);
      }
    },
    [items, load, onCatchupChanged],
  );

  const setParam = (key: string, value: string | null) => replaceParams({ [key]: value });

  const focused = focus >= 0 ? items[focus] : undefined;

  const move = (delta: number) => {
    if (!items.length) return;
    const next = Math.max(0, Math.min(items.length - 1, focus + delta));
    setFocus(next);
    // Keyboard navigation: jump, don't glide — it fires dozens of times a session.
    cardRefs.current[next]?.scrollIntoView({ block: "nearest" });
  };

  const togglePanel = (panel: Exclude<Panel, null>) => {
    if (!focused) return;
    if (panel === "coverage" && focused.source_count < 2) return;
    if (panel === "comments" && !focused.discussions.length) return;
    setPanels((p) => ({ ...p, [focused.id]: p[focused.id] === panel ? null : panel }));
  };

  useHotkeys({
    j: () => move(1),
    k: () => move(-1),
    ArrowDown: () => move(1),
    ArrowUp: () => move(-1),
    o: () => {
      if (!focused) return;
      onOpen(focused.lead);
      window.open(focused.lead.url, "_blank", "noopener,noreferrer");
    },
    Enter: () => {
      if (!focused) return;
      onOpen(focused.lead);
      window.open(focused.lead.url, "_blank", "noopener,noreferrer");
    },
    s: () => focused && onToggleSave(focused.lead),
    x: () => focused && onHide(focused),
    e: () => togglePanel("coverage"),
    c: () => togglePanel("comments"),
    "/": () => searchRef.current?.focus(),
    f: () => setParam("view", "foryou"),
    t: () => setParam("view", "top"),
    l: () => setParam("view", "latest"),
    Escape: () => {
      if (q || query) {
        setQuery("");
        setParam("q", null);
      } else setFocus(-1);
    },
  });

  const activeView = VIEWS.find((v) => v.id === view)!;
  const filtered = Boolean(topic || source || q);

  const subtitle = useMemo(() => {
    if (!feed) return "Loading…";
    if (q) return `${plural(feed.total, "result")} for “${q}” across everything stored`;
    const parts = [plural(feed.total, "story", "stories")];
    if (status?.last_updated) parts.push(`updated ${ago(status.last_updated)}`);
    return `${parts.join(" · ")} — ${activeView.hint.toLowerCase()}`;
  }, [feed, q, status?.last_updated, activeView.hint]);

  let lastDay = "";
  // In Latest, a divider marks where "new since last time" ends — only worth
  // showing if you've been away a while and there's something on both sides.
  const firstSeen =
    lastVisit && Date.now() / 1000 - lastVisit > 20 * 60
      ? items.findIndex((c) => c.lead.published_at <= lastVisit)
      : -1;
  const sinceIndex = firstSeen > 0 ? firstSeen : -1;

  return (
    <div className="today">
      <div>
        <div className="page-head">
          <div>
            <h1 className="page-title">{q ? "Search" : view === "foryou" ? "Today, for you" : view === "top" ? "Top stories" : "Latest"}</h1>
            <p className="page-sub">{subtitle}</p>
          </div>
        </div>

        <div className="toolbar">
          <div className="toolbar-row">
            <div className="seg" role="group" aria-label="Feed view">
              {VIEWS.map((v) => (
                <button key={v.id} type="button" aria-pressed={view === v.id} title={`${v.hint} (${v.id[0]})`} onClick={() => setParam("view", v.id)}>
                  <v.icon size={14} aria-hidden />
                  {v.label}
                </button>
              ))}
            </div>
            <label className="search">
              <Search size={15} aria-hidden />
              <span className="sr-only">Search stories</span>
              <input
                ref={searchRef}
                type="search"
                placeholder="Search stories, names, topics…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Escape") {
                    setQuery("");
                    setParam("q", null);
                    (e.target as HTMLInputElement).blur();
                  }
                }}
              />
              {!query && <kbd>/</kbd>}
            </label>
            <select className="select" value={source ?? ""} onChange={(e) => setParam("source", e.target.value || null)} aria-label="Filter by source">
              <option value="">All sources</option>
              {meta.sources.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </div>
          <div className="chips scroll" role="group" aria-label="Filter by topic">
            <button type="button" className="chip" aria-pressed={!topic} onClick={() => setParam("topic", null)}>
              Everything
            </button>
            {meta.topics.map((t) => (
              <button key={t.id} type="button" className="chip" aria-pressed={topic === t.id} onClick={() => setParam("topic", topic === t.id ? null : t.id)}>
                {t.label}
              </button>
            ))}
          </div>
        </div>

        {view === "foryou" && feed && !feed.personalised && !filtered && (
          <div className="banner">
            <Sparkles size={16} aria-hidden />
            <span>
              This is the Top ranking until you've told Patch Notes what you like. A quick{" "}
              <a href="#/catchup" style={{ color: "var(--accent)", fontWeight: 500 }}>
                catch-up
              </a>{" "}
              is the fastest way to teach it.
            </span>
          </div>
        )}

        {hasNewer && items.length > 0 && !loading && (
          <div className="banner">
            <RefreshCw size={16} aria-hidden />
            <span style={{ flex: 1 }}>New stories have come in since you loaded this page.</span>
            <button type="button" className="btn btn-accent" style={{ height: 30 }} onClick={() => load(0)}>
              Show them
            </button>
          </div>
        )}

        {error && (
          <div className="banner" data-tone="error">
            <X size={16} aria-hidden />
            <span style={{ flex: 1 }}>{error}</span>
            <button type="button" className="btn" style={{ height: 30 }} onClick={() => load(0)}>
              Retry
            </button>
          </div>
        )}

        <div className="feed" data-loading={loading && items.length > 0} data-entering={entering}>
          {!feed && loading && <Skeleton />}
          {feed && items.length === 0 && !loading && (
            filtered ? (
              <Empty icon={<Search size={22} />} title="Nothing matches">
                Try another topic or source, or clear the search.
              </Empty>
            ) : status?.fetching || !status?.story_count ? (
              <Empty icon={<RefreshCw size={22} />} title="Fetching the first batch…">
                Pulling stories from {meta.sources.length} sources. This takes a few seconds the first time.
              </Empty>
            ) : (
              <Empty icon={<Inbox size={22} />} title="All quiet">
                Nothing new in the last couple of days.
              </Empty>
            )
          )}
          {items.map((c, i) => {
            const day = view === "latest" ? dayLabel(c.lead.published_at) : "";
            const showDay = view === "latest" && day !== lastDay;
            lastDay = day;
            const isNew = Boolean(lastVisit && c.first_published > lastVisit);
            const showSince = view === "latest" && i === sinceIndex;
            return (
              <Fragment key={c.id}>
                {showDay && <div className="day-head">{day}</div>}
                {showSince && lastVisit && (
                  <div className="since" role="separator">
                    you were last here {timeAgoLong(lastVisit)}
                  </div>
                )}
                <div
                  className="story-slot"
                  data-leaving={leaving.has(c.id)}
                  style={{ ["--i" as string]: i }}
                >
                <StoryCard
                  ref={(el) => {
                    cardRefs.current[i] = el;
                  }}
                  cluster={c}
                  focused={i === focus}
                  panel={panels[c.id] ?? null}
                  onPanel={(p) => setPanels((prev) => ({ ...prev, [c.id]: p }))}
                  onOpen={onOpen}
                  onToggleSave={onToggleSave}
                  onHide={onHide}
                  onTopic={(id) => setParam("topic", id)}
                  onFocus={() => setFocus(i)}
                  showReasons={view === "foryou"}
                  isNew={isNew}
                />
                </div>
              </Fragment>
            );
          })}
          {feed?.has_more && (
            <div className="feed-foot">
              <button type="button" className="btn" disabled={loading} onClick={() => load(items.length)}>
                {loading ? "Loading…" : `Show more (${feed.total - items.length} left)`}
              </button>
            </div>
          )}
        </div>
      </div>
      <Rail status={status} catchupCount={catchupCount} />
      <button
        type="button"
        className="to-top"
        data-visible={scrolled}
        aria-hidden={!scrolled}
        tabIndex={scrolled ? 0 : -1}
        onClick={() => window.scrollTo({ top: 0, behavior: reduceMotion ? "auto" : "smooth" })}
      >
        <ArrowUp size={15} aria-hidden /> Back to top
      </button>
    </div>
  );
}
