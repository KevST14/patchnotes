import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { ArrowLeft, ArrowRight, ArrowUp, Bookmark, Check, ExternalLink, PartyPopper, RefreshCw, Undo2, X } from "lucide-react";
import { api } from "../api";
import { Empty, Skeleton } from "../components/Bits";
import { SwipeDeck, type DeckHandle, type Decision } from "../components/SwipeDeck";
import { useHashRoute, useHotkeys, useMeta, useReducedMotion } from "../hooks";
import type { Cluster, Prefs, Profile, Story } from "../types";
import { plural } from "../utils";

interface Props {
  onChanged: () => void;
}

export function CatchUpView({ onChanged }: Props) {
  const { navigate } = useHashRoute();
  const reduceMotion = useReducedMotion();
  const deck = useRef<DeckHandle>(null);

  const [queue, setQueue] = useState<Cluster[] | null>(null);
  const [total, setTotal] = useState(0);
  const [remainingOnServer, setRemainingOnServer] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<{ cluster: Cluster; decision: Decision }[]>([]);
  const [returning, setReturning] = useState<{ decision: Decision; nonce: number } | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [prefs, setPrefs] = useState<Prefs | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const res = await api.catchup(40);
      setQueue(res.items);
      setTotal(res.items.length);
      setRemainingOnServer(res.remaining);
      setHistory([]);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  const refreshProfile = useCallback(() => {
    api.profile().then(setProfile).catch(() => undefined);
  }, []);

  useEffect(() => {
    load();
    refreshProfile();
    api.prefs().then(setPrefs).catch(() => undefined);
  }, [load, refreshProfile]);

  // Re-read the profile shortly after each decision so the bars move as you go.
  const profileTimer = useRef<number | undefined>(undefined);
  const scheduleProfile = useCallback(() => {
    window.clearTimeout(profileTimer.current);
    profileTimer.current = window.setTimeout(refreshProfile, 350);
  }, [refreshProfile]);

  const onDecide = useCallback(
    (cluster: Cluster, decision: Decision) => {
      setQueue((q) => (q ? q.filter((c) => c.id !== cluster.id) : q));
      setHistory((h) => [...h, { cluster, decision }]);
      setReturning(null);
      api
        .interact(cluster.lead.id, decision)
        .then(() => {
          scheduleProfile();
          onChanged();
        })
        .catch((e: Error) => toast.error(e.message));
    },
    [scheduleProfile, onChanged],
  );

  const undo = useCallback(async () => {
    const last = history[history.length - 1];
    if (!last || deck.current?.busy()) return;
    setHistory((h) => h.slice(0, -1));
    setQueue((q) => [last.cluster, ...(q ?? [])]);
    setReturning({ decision: last.decision, nonce: Date.now() });
    try {
      await api.undo(last.cluster.lead.id);
      scheduleProfile();
      onChanged();
    } catch (e) {
      toast.error((e as Error).message);
    }
  }, [history, scheduleProfile, onChanged]);

  const onOpen = useCallback((story: Story) => {
    api.interact(story.id, "open").catch(() => undefined);
  }, []);

  const openTop = () => {
    const top = queue?.[0];
    if (!top) return;
    onOpen(top.lead);
    window.open(top.lead.url, "_blank", "noopener,noreferrer");
  };

  const toggleFollow = async (topicId: string) => {
    if (!prefs) return;
    const followed = prefs.followed_topics.includes(topicId)
      ? prefs.followed_topics.filter((t) => t !== topicId)
      : [...prefs.followed_topics, topicId];
    setPrefs({ ...prefs, followed_topics: followed });
    try {
      setPrefs(await api.setPrefs({ followed_topics: followed }));
      refreshProfile();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  const done = queue !== null && queue.length === 0;

  useHotkeys(
    {
      ArrowRight: () => deck.current?.fling("keep"),
      l: () => deck.current?.fling("keep"),
      ArrowLeft: () => deck.current?.fling("skip"),
      h: () => deck.current?.fling("skip"),
      ArrowUp: () => deck.current?.fling("save"),
      s: () => deck.current?.fling("save"),
      " ": openTop,
      o: openTop,
      Enter: openTop,
      z: undo,
      Backspace: undo,
    },
    !done,
  );

  const counts = history.reduce(
    (acc, h) => ({ ...acc, [h.decision]: acc[h.decision] + 1 }),
    { keep: 0, skip: 0, save: 0 } as Record<Decision, number>,
  );
  const reviewed = history.length;

  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="page-title">Catch up</h1>
          <p className="page-sub">
            The last day and a half, best first, one story at a time. Every keep, skip and save tunes your For You feed.
          </p>
        </div>
      </div>

      <div className="catchup">
        <div className="deck-wrap">
          {error && (
            <div className="banner" data-tone="error" style={{ width: "100%", maxWidth: 560 }}>
              <X size={16} aria-hidden /> <span style={{ flex: 1 }}>{error}</span>
              <button className="btn" type="button" onClick={load}>
                Retry
              </button>
            </div>
          )}
          {queue === null && !error && (
            <div style={{ width: "100%", maxWidth: 560 }}>
              <Skeleton rows={3} />
            </div>
          )}

          {queue && total === 0 && (
            <Empty icon={<Check size={22} />} title="You're all caught up" action={
              <button type="button" className="btn" onClick={() => navigate("today")}>
                Back to the feed
              </button>
            }>
              Nothing you haven't already seen from the last day and a half. New stories arrive every few minutes.
            </Empty>
          )}

          {queue && total > 0 && !done && (
            <>
              <div className="progress" aria-label={`${reviewed} of ${total} reviewed`}>
                <span>
                  {reviewed + 1} / {total}
                </span>
                <div className="progress-track">
                  <div className="progress-fill" style={{ transform: `scaleX(${reviewed / total})` }} />
                </div>
                <span>{plural(queue.length, "left", "left")}</span>
              </div>
              <SwipeDeck ref={deck} cards={queue} onDecide={onDecide} onOpen={onOpen} returning={returning} reduceMotion={reduceMotion} />
              <div className="deck-controls">
                <button type="button" className="deck-btn small" onClick={undo} disabled={!history.length} aria-label="Undo (z)" title="Undo (z)">
                  <Undo2 size={18} />
                </button>
                <button type="button" className="deck-btn skip" onClick={() => deck.current?.fling("skip")} aria-label="Skip (left arrow)" title="Skip (←)">
                  <X size={24} />
                </button>
                <button type="button" className="deck-btn save" onClick={() => deck.current?.fling("save")} aria-label="Save for later (up arrow)" title="Save (↑)">
                  <Bookmark size={21} />
                </button>
                <button type="button" className="deck-btn keep" onClick={() => deck.current?.fling("keep")} aria-label="Keep (right arrow)" title="Keep (→)">
                  <Check size={24} />
                </button>
                <button type="button" className="deck-btn small" onClick={openTop} aria-label="Open story (space)" title="Open (space)">
                  <ExternalLink size={18} />
                </button>
              </div>
              <div className="deck-hints">
                <span>
                  <kbd><ArrowLeft size={11} /></kbd> skip
                </span>
                <span>
                  <kbd><ArrowRight size={11} /></kbd> keep
                </span>
                <span>
                  <kbd><ArrowUp size={11} /></kbd> save
                </span>
                <span>
                  <kbd>space</kbd> open
                </span>
                <span>
                  <kbd>z</kbd> undo
                </span>
              </div>
            </>
          )}

          {done && total > 0 && (
            <div className="card done-card">
              <span className="empty" style={{ padding: 0 }}>
                <span className="icon-wrap">
                  <PartyPopper size={22} />
                </span>
              </span>
              <h2>Caught up</h2>
              <p className="muted" style={{ margin: 0 }}>
                {remainingOnServer > total
                  ? `That was the best ${total}. There are ${remainingOnServer - total} more if you're keen.`
                  : "That's everything from the last day and a half."}
              </p>
              <div className="done-stats">
                <div>
                  <b style={{ color: "var(--keep)" }}>{counts.keep}</b>
                  <span>kept</span>
                </div>
                <div>
                  <b style={{ color: "var(--save)" }}>{counts.save}</b>
                  <span>saved</span>
                </div>
                <div>
                  <b style={{ color: "var(--skip)" }}>{counts.skip}</b>
                  <span>skipped</span>
                </div>
              </div>
              <div style={{ display: "flex", gap: 10, justifyContent: "center", flexWrap: "wrap" }}>
                <button type="button" className="btn btn-primary" onClick={() => navigate("today", { view: "foryou" })}>
                  See your For You feed
                </button>
                {counts.save > 0 && (
                  <button type="button" className="btn" onClick={() => navigate("saved")}>
                    Read saved ({counts.save})
                  </button>
                )}
                {remainingOnServer > total && (
                  <button type="button" className="btn" onClick={load}>
                    <RefreshCw size={15} aria-hidden /> Keep going
                  </button>
                )}
                <button type="button" className="btn btn-ghost" onClick={undo}>
                  <Undo2 size={15} aria-hidden /> Undo last
                </button>
              </div>
            </div>
          )}
        </div>

        <LearningPanel profile={profile} prefs={prefs} onToggleFollow={toggleFollow} />
      </div>
    </div>
  );
}

function LearningPanel({
  profile,
  prefs,
  onToggleFollow,
}: {
  profile: Profile | null;
  prefs: Prefs | null;
  onToggleFollow: (topicId: string) => void;
}) {
  const { meta } = useMeta();
  const rows = profile?.topics.filter((t) => Math.abs(t.affinity) > 0.005) ?? [];
  const scale = Math.max(1, ...rows.map((r) => Math.abs(r.affinity)));

  return (
    <aside className="card learn" aria-live="polite">
      <h3>What your feed is learning</h3>
      <p>
        {profile && profile.signals > 0
          ? `Based on ${plural(profile.signals, "thing")} you've kept, saved, opened or skipped.`
          : "Nothing yet. Keep a few stories and watch these move."}
      </p>

      {rows.length > 0 && (
        <div style={{ marginBottom: 18 }}>
          {rows.slice(0, 8).map((r) => (
            <div className="aff-row" key={r.id} title={`${r.signals} signal${r.signals === 1 ? "" : "s"}`}>
              <span className="lbl">{r.label}</span>
              <span className="aff-track">
                <span
                  className="aff-bar"
                  data-neg={r.affinity < 0}
                  style={{ transform: `scaleX(${Math.min(1, Math.abs(r.affinity) / scale)})` }}
                />
              </span>
              <span className="val">{r.affinity > 0 ? "+" : ""}{r.affinity.toFixed(2)}</span>
            </div>
          ))}
        </div>
      )}

      {profile && (profile.liked_terms.length > 0 || profile.disliked_terms.length > 0) && (
        <>
          <h4 className="section-title">Names and phrases</h4>
          <div className="term-cloud" style={{ marginBottom: 18 }}>
            {profile.liked_terms.slice(0, 8).map((t) => (
              <span className="term" data-tone="like" key={t.id}>
                {t.label}
              </span>
            ))}
            {profile.disliked_terms.slice(0, 5).map((t) => (
              <span className="term" data-tone="dislike" key={t.id}>
                {t.label}
              </span>
            ))}
          </div>
        </>
      )}

      <h4 className="section-title">Follow topics</h4>
      <p style={{ marginBottom: 10 }}>Followed topics get a permanent boost, on top of what it learns.</p>
      <div className="chips">
        {meta.topics.map((t) => (
          <button
            type="button"
            key={t.id}
            className="chip"
            aria-pressed={prefs?.followed_topics.includes(t.id) ?? false}
            onClick={() => onToggleFollow(t.id)}
            disabled={!prefs}
          >
            {prefs?.followed_topics.includes(t.id) && <Check size={13} aria-hidden />}
            {t.label}
          </button>
        ))}
      </div>
    </aside>
  );
}
