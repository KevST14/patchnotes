import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Toaster, toast } from "sonner";
import { Keyboard, Moon, RefreshCw, Settings2, Sun } from "lucide-react";
import { api } from "./api";
import { Empty } from "./components/Bits";
import { SettingsDialog, ShortcutsDialog } from "./components/Dialogs";
import {
  MetaContext,
  buildMeta,
  useAsync,
  useHashRoute,
  useHotkeys,
  useInterval,
  useTheme,
  type Tab,
} from "./hooks";
import type { Status } from "./types";
import { ago, editionVersion, isTypingTarget } from "./utils";
import { CatchUpView } from "./views/CatchUpView";
import { TodayView } from "./views/TodayView";

const TAB_META: { id: Tab; label: string; key: string }[] = [
  { id: "today", label: "Today", key: "t" },
  { id: "catchup", label: "Catch up", key: "c" },
];

export default function App() {
  const metaReq = useAsync(() => api.meta(), []);
  const meta = useMemo(() => (metaReq.data ? buildMeta(metaReq.data) : null), [metaReq.data]);
  const { tab, navigate } = useHashRoute();
  const theme = useTheme();
  const [status, setStatus] = useState<Status | null>(null);
  const [catchupCount, setCatchupCount] = useState<number | null>(null);
  const [showShortcuts, setShowShortcuts] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [, setTick] = useState(0);
  // Only a refresh you asked for gets a toast; background fetches every ten
  // minutes would make that noisy (the feed shows a quiet banner instead).
  const manualRefresh = useRef<number | null>(null);

  const pollStatus = useCallback(() => {
    api
      .status()
      .then((s) => {
        // Wait for a cycle that finished *after* the button was pressed.
        if (manualRefresh.current && !s.fetching && (s.last_run.finished ?? 0) > manualRefresh.current) {
          manualRefresh.current = null;
          const n = s.last_run.new;
          toast(n > 0 ? `${n} new ${n === 1 ? "story" : "stories"}` : "Up to date — nothing new yet");
        }
        setStatus(s);
      })
      .catch(() => undefined);
  }, []);

  const refreshCatchup = useCallback(() => {
    api
      .catchup(1)
      .then((r) => setCatchupCount(r.remaining))
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!meta) return;
    pollStatus();
  }, [meta, pollStatus]);
  // Poll quickly while a fetch is running, gently otherwise.
  useInterval(pollStatus, meta ? (status?.fetching ? 2500 : 30000) : null);
  // Re-render relative times ("updated 3m ago") every half minute.
  useInterval(() => setTick((t) => t + 1), 30000);
  useEffect(() => {
    if (meta) refreshCatchup();
  }, [meta, status?.last_updated, refreshCatchup]);

  const refresh = useCallback(async () => {
    try {
      const r = await api.refresh();
      manualRefresh.current = Date.now() / 1000 - 1;
      setStatus((s) => (s ? { ...s, fetching: true } : s));
      if (r.status === "already-running") toast("Already fetching — hang on");
      window.setTimeout(pollStatus, 800);
    } catch (e) {
      toast.error((e as Error).message);
    }
  }, [pollStatus]);

  // "g" then a letter jumps between tabs (Gmail-style), so single letters
  // stay free for each view's own shortcuts.
  const gPending = useRef<number | null>(null);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey || isTypingTarget(e.target)) return;
      if (document.querySelector("dialog[open]")) return;
      if (gPending.current !== null) {
        window.clearTimeout(gPending.current);
        gPending.current = null;
        const target = TAB_META.find((t) => t.key === e.key);
        e.preventDefault();
        e.stopImmediatePropagation();
        if (target) navigate(target.id);
        return;
      }
      if (e.key === "g") {
        e.preventDefault();
        e.stopImmediatePropagation();
        gPending.current = window.setTimeout(() => (gPending.current = null), 1200);
      }
    };
    window.addEventListener("keydown", onKey, { capture: true });
    return () => window.removeEventListener("keydown", onKey, { capture: true });
  }, [navigate]);

  useHotkeys(
    {
      "?": () => setShowShortcuts(true),
      ",": () => setShowSettings(true),
      r: refresh,
    },
    Boolean(meta) && !showShortcuts && !showSettings,
  );

  if (!meta) {
    return (
      <div className="shell" style={{ paddingTop: 80 }}>
        {metaReq.error ? (
          <Empty
            icon={<RefreshCw size={22} />}
            title="Can't reach the backend"
            action={
              <button type="button" className="btn btn-primary" onClick={() => metaReq.reload()}>
                Try again
              </button>
            }
          >
            Start it with <code className="mono">uvicorn app.main:app --reload</code> in <code className="mono">backend/</code>, then try again.
          </Empty>
        ) : (
          <p className="muted" style={{ textAlign: "center" }}>
            Loading Patch Notes…
          </p>
        )}
      </div>
    );
  }

  const failing = status?.sources.filter((s) => s.error).length ?? 0;
  const liveState = status?.fetching ? "fetching" : status && failing > status.sources.length / 2 ? "error" : "ok";

  return (
    <MetaContext.Provider value={meta}>
      <header className="masthead">
        <div className="masthead-inner">
          <div className="masthead-row">
            <a className="brand" href="#/today" aria-label="Patch Notes, home">
              <span className="wordmark">
                Patch <em>Notes</em>
              </span>
              <span className="edition">
                <b>{editionVersion()}</b>
                <span className="long"> · the tech world, changelogged</span>
              </span>
            </a>
            <div className="masthead-status" title={status?.last_updated ? new Date(status.last_updated * 1000).toLocaleString() : undefined}>
              <span className="live-dot" data-state={liveState} aria-hidden />
              <span className="label tick">
                {status?.fetching
                  ? "fetching…"
                  : status?.last_updated
                    ? `updated ${ago(status.last_updated)}`
                    : "waiting for first fetch"}
              </span>
            </div>
            <div className="masthead-actions">
              <button type="button" className="icon-btn" onClick={refresh} aria-label="Fetch new stories now (r)" title="Fetch new stories now (r)">
                <RefreshCw size={17} className={status?.fetching ? "spin" : undefined} />
              </button>
              <button
                type="button"
                className="icon-btn"
                onClick={theme.toggle}
                aria-label={theme.resolved === "dark" ? "Switch to light theme" : "Switch to dark theme"}
                title="Toggle theme"
              >
                {theme.resolved === "dark" ? <Sun size={17} /> : <Moon size={17} />}
              </button>
              <button type="button" className="icon-btn" onClick={() => setShowSettings(true)} aria-label="Settings (,)" title="Settings (,)">
                <Settings2 size={17} />
              </button>
              <button type="button" className="icon-btn" onClick={() => setShowShortcuts(true)} aria-label="Keyboard shortcuts (?)" title="Keyboard shortcuts (?)">
                <Keyboard size={17} />
              </button>
            </div>
          </div>
          <nav className="tabs" aria-label="Sections">
            {TAB_META.map((t) => (
              <a key={t.id} className="tab" href={`#/${t.id}`} aria-current={tab === t.id ? "page" : undefined}>
                {t.label}
                {t.id === "catchup" && catchupCount !== null && catchupCount > 0 && <span className="count">{catchupCount > 99 ? "99+" : catchupCount}</span>}
                <kbd>g {t.key}</kbd>
              </a>
            ))}
          </nav>
        </div>
      </header>

      <main className="shell">
        {tab === "today" && <TodayView status={status} catchupCount={catchupCount} onCatchupChanged={refreshCatchup} />}
        {tab === "catchup" && <CatchUpView onChanged={refreshCatchup} />}
      </main>

      <ShortcutsDialog open={showShortcuts} onClose={() => setShowShortcuts(false)} />
      <SettingsDialog open={showSettings} onClose={() => setShowSettings(false)} theme={theme.choice} setTheme={theme.setChoice} />
      <Toaster position="bottom-left" theme={theme.resolved} toastOptions={{ duration: 3500 }} />
    </MetaContext.Provider>
  );
}
