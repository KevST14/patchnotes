import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import type { Meta, Source, Topic } from "./types";
import { isTypingTarget } from "./utils";

/**
 * Fetch on mount and whenever `deps` change. While a refetch is in flight the
 * previous data stays on screen (callers dim it with `loading`), so the page
 * never flashes back to a skeleton.
 */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const seq = useRef(0);

  const run = useCallback(() => {
    const id = ++seq.current;
    setLoading(true);
    return fn()
      .then((result) => {
        if (id === seq.current) {
          setData(result);
          setError(null);
        }
        return result;
      })
      .catch((err: Error) => {
        if (id === seq.current) setError(err.message);
      })
      .finally(() => {
        if (id === seq.current) setLoading(false);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    run();
  }, [run]);

  return { data, setData, error, loading, reload: run };
}

export type Tab = "today" | "catchup" | "trends" | "quiz" | "saved";
export const TABS: Tab[] = ["today", "catchup", "trends", "quiz", "saved"];

function readHash(): { tab: Tab; params: URLSearchParams } {
  const raw = window.location.hash.replace(/^#\/?/, "");
  const [path, query = ""] = raw.split("?");
  const tab = (TABS as string[]).includes(path) ? (path as Tab) : "today";
  return { tab, params: new URLSearchParams(query) };
}

/** The active tab (and its filters) live in the URL hash, so back/forward and bookmarks work. */
export function useHashRoute() {
  const [route, setRoute] = useState(readHash);

  useEffect(() => {
    const onChange = () => setRoute(readHash());
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);

  const navigate = useCallback((tab: Tab, params?: Record<string, string | null | undefined>) => {
    const search = new URLSearchParams();
    for (const [k, v] of Object.entries(params ?? {})) if (v) search.set(k, v);
    const query = search.toString();
    window.location.hash = `/${tab}${query ? `?${query}` : ""}`;
  }, []);

  /** Update params on the current tab without adding a history entry for every keystroke. */
  const replaceParams = useCallback((params: Record<string, string | null | undefined>) => {
    const current = readHash();
    const search = new URLSearchParams(current.params);
    for (const [k, v] of Object.entries(params)) {
      if (v) search.set(k, v);
      else search.delete(k);
    }
    const query = search.toString();
    const url = `${window.location.pathname}${window.location.search}#/${current.tab}${query ? `?${query}` : ""}`;
    window.history.replaceState(null, "", url);
    setRoute(readHash());
  }, []);

  return { ...route, navigate, replaceParams };
}

type HotkeyMap = Record<string, (e: KeyboardEvent) => void>;

/**
 * Single-key shortcuts, ignored while typing in a field or when a modifier
 * is held (so Cmd+R etc. still work). Keys are KeyboardEvent.key values.
 */
export function useHotkeys(map: HotkeyMap, enabled = true) {
  const ref = useRef(map);
  ref.current = map;
  useEffect(() => {
    if (!enabled) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey || isTypingTarget(e.target)) return;
      // Enter/Space on a focused button or link belong to that control.
      if ((e.key === "Enter" || e.key === " ") && e.target instanceof Element && e.target.closest("button, a, [role=button], summary")) return;
      const handler = ref.current[e.key];
      if (handler) {
        e.preventDefault();
        handler(e);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [enabled]);
}

export function useInterval(fn: () => void, ms: number | null) {
  const ref = useRef(fn);
  ref.current = fn;
  useEffect(() => {
    if (ms === null) return;
    const id = window.setInterval(() => ref.current(), ms);
    return () => window.clearInterval(id);
  }, [ms]);
}

export function useReducedMotion(): boolean {
  const [reduce, setReduce] = useState(() => window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const onChange = () => setReduce(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);
  return reduce;
}

export type ThemeChoice = "light" | "dark" | "system";

export function useTheme() {
  const [choice, setChoice] = useState<ThemeChoice>(() => {
    try {
      const saved = localStorage.getItem("pn-theme");
      return saved === "light" || saved === "dark" ? saved : "system";
    } catch {
      return "system";
    }
  });

  useEffect(() => {
    const root = document.documentElement;
    if (choice === "system") delete root.dataset.theme;
    else root.dataset.theme = choice;
    try {
      if (choice === "system") localStorage.removeItem("pn-theme");
      else localStorage.setItem("pn-theme", choice);
    } catch {
      /* storage unavailable; the choice just won't persist */
    }
  }, [choice]);

  const resolved: "light" | "dark" =
    choice === "system" ? (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light") : choice;

  const toggle = useCallback(() => setChoice(resolved === "dark" ? "light" : "dark"), [resolved]);
  return { choice, resolved, toggle, setChoice };
}

/** Sources and topics, loaded once and shared everywhere. */
export interface MetaValue {
  meta: Meta;
  source: (id: string) => Source;
  topic: (id: string) => Topic | undefined;
}

export const MetaContext = createContext<MetaValue | null>(null);

export function useMeta(): MetaValue {
  const value = useContext(MetaContext);
  if (!value) throw new Error("useMeta outside MetaContext");
  return value;
}

export function buildMeta(meta: Meta): MetaValue {
  const sources = new Map(meta.sources.map((s) => [s.id, s]));
  const topics = new Map(meta.topics.map((t) => [t.id, t]));
  return {
    meta,
    source: (id) =>
      sources.get(id) ?? { id, name: id, short: id, kind: "rss", homepage: "", color: "#888" },
    topic: (id) => topics.get(id),
  };
}

/**
 * When you were last here (unix seconds), read once per page load. The
 * current time is written when the tab is hidden or closed, so the *next*
 * visit can mark what's new since this one.
 */
export function useLastVisit(): number | null {
  const [last] = useState<number | null>(() => {
    try {
      const raw = localStorage.getItem("pn-last-visit");
      return raw ? Number(raw) : null;
    } catch {
      return null;
    }
  });
  useEffect(() => {
    const save = () => {
      try {
        localStorage.setItem("pn-last-visit", String(Math.floor(Date.now() / 1000)));
      } catch {
        /* storage unavailable */
      }
    };
    const onVisibility = () => document.visibilityState === "hidden" && save();
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("pagehide", save);
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("pagehide", save);
    };
  }, []);
  return last;
}

export function useScrolledPast(px: number): boolean {
  const [past, setPast] = useState(false);
  useEffect(() => {
    const onScroll = () => setPast(window.scrollY > px);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [px]);
  return past;
}
