import { forwardRef, useImperativeHandle, useLayoutEffect, useRef, useState } from "react";
import { ArrowUp, MessageSquare, Sparkles } from "lucide-react";
import { springEasing } from "../spring";
import type { Cluster, Story } from "../types";
import { compact, timeAgo } from "../utils";
import { SourceMark, SourceStack } from "./Bits";
import { useMeta } from "../hooks";

export type Decision = "keep" | "skip" | "save";

export interface DeckHandle {
  /** Throw the top card in a direction (keyboard / buttons). */
  fling: (decision: Decision) => void;
  /** True while a card is mid-flight; undo waits for it to land. */
  busy: () => boolean;
}

interface Props {
  cards: Cluster[];
  onDecide: (cluster: Cluster, decision: Decision) => void;
  onOpen: (story: Story) => void;
  /** Set after an undo: the card comes back from where it left. */
  returning: { decision: Decision; nonce: number } | null;
  reduceMotion: boolean;
}

// How far (px) or how fast (px/ms) a drag must go to count as a decision.
const DISTANCE = 110;
const FLICK = 0.45;
const EASE_OUT = "cubic-bezier(0.23, 1, 0.32, 1)";

interface DragState {
  pointerId: number;
  x0: number;
  y0: number;
  dx: number;
  dy: number;
  moved: boolean;
  trail: { t: number; x: number; y: number }[];
}

function decisionFor(dx: number, dy: number, vx: number, vy: number): Decision | null {
  const horizontal = Math.abs(dx) >= Math.abs(dy);
  if (horizontal) {
    if (dx > DISTANCE || (vx > FLICK && dx > 24)) return "keep";
    if (dx < -DISTANCE || (vx < -FLICK && dx < -24)) return "skip";
  } else if (dy < -DISTANCE || (vy < -FLICK && dy < -24)) {
    return "save";
  }
  return null;
}

function offscreen(decision: Decision, el: HTMLElement, dx = 0, dy = 0, vx = 0, vy = 0) {
  const w = window.innerWidth;
  const h = window.innerHeight;
  if (decision === "keep") return { x: w * 0.55 + el.offsetWidth, y: dy + vy * 140, r: 16 };
  if (decision === "skip") return { x: -(w * 0.55 + el.offsetWidth), y: dy + vy * 140, r: -16 };
  return { x: dx + vx * 140, y: -(h * 0.5 + el.offsetHeight), r: dx * 0.03 };
}

export const SwipeDeck = forwardRef<DeckHandle, Props>(function SwipeDeck(
  { cards, onDecide, onOpen, returning, reduceMotion },
  ref,
) {
  const topRef = useRef<HTMLDivElement>(null);
  const stamps = useRef<Record<Decision, HTMLDivElement | null>>({ keep: null, skip: null, save: null });
  const drag = useRef<DragState | null>(null);
  const busy = useRef(false);
  const suppressClick = useRef(false);
  const top = cards[0];

  function setStamps(keep: number, skip: number, save: number) {
    if (stamps.current.keep) stamps.current.keep.style.opacity = String(keep);
    if (stamps.current.skip) stamps.current.skip.style.opacity = String(skip);
    if (stamps.current.save) stamps.current.save.style.opacity = String(save);
  }

  function fly(decision: Decision, dx = 0, dy = 0, vx = 0, vy = 0) {
    const el = topRef.current;
    if (!el || busy.current || !top) return;
    busy.current = true;
    setStamps(decision === "keep" ? 1 : 0, decision === "skip" ? 1 : 0, decision === "save" ? 1 : 0);
    const from = el.style.transform || "none";
    el.style.transition = "none";
    const target = offscreen(decision, el, dx, dy, vx, vy);
    const distance = Math.hypot(target.x - dx, target.y - dy);
    const speed = Math.hypot(vx, vy);
    // A hard flick leaves at its own speed; a key press is quick and plain.
    const duration = reduceMotion ? 160 : Math.round(Math.min(300, Math.max(170, distance / Math.max(speed, 2.6))));
    const frames = reduceMotion
      ? [{ opacity: 1 }, { opacity: 0 }]
      : [{ transform: from }, { transform: `translate(${target.x}px, ${target.y}px) rotate(${target.r}deg)` }];
    const anim = el.animate(frames, { duration, easing: EASE_OUT, fill: "forwards" });
    anim.onfinish = () => {
      busy.current = false;
      onDecide(top, decision);
    };
  }

  useImperativeHandle(ref, () => ({ fling: (d) => fly(d), busy: () => busy.current }));

  // An undone card flies back in from the side it left on.
  useLayoutEffect(() => {
    const el = topRef.current;
    if (!returning || !el) return;
    const target = offscreen(returning.decision, el);
    el.animate(
      reduceMotion
        ? [{ opacity: 0 }, { opacity: 1 }]
        : [{ transform: `translate(${target.x}px, ${target.y}px) rotate(${target.r}deg)` }, { transform: "none" }],
      { duration: reduceMotion ? 160 : 280, easing: EASE_OUT },
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [returning?.nonce]);

  // Fresh top card: clear anything left over from the previous drag.
  useLayoutEffect(() => {
    setStamps(0, 0, 0);
    const el = topRef.current;
    if (el) {
      el.style.transform = "";
      el.style.transition = "";
    }
  }, [top?.id]);

  // The drag listens on window rather than the card, so a fast flick that
  // leaves the card in a single frame still counts, and no pointer capture
  // is needed — which keeps a plain click on the headline a normal link click.
  function onPointerDown(e: React.PointerEvent<HTMLDivElement>) {
    if (busy.current || e.button !== 0 || !e.isPrimary) return; // ignore a second finger
    const el = e.currentTarget;
    const d: DragState = {
      pointerId: e.pointerId,
      x0: e.clientX,
      y0: e.clientY,
      dx: 0,
      dy: 0,
      moved: false,
      trail: [{ t: performance.now(), x: e.clientX, y: e.clientY }],
    };
    drag.current = d;

    const move = (ev: PointerEvent) => {
      if (ev.pointerId !== d.pointerId) return;
      const rawX = ev.clientX - d.x0;
      const rawY = ev.clientY - d.y0;
      if (!d.moved) {
        if (Math.hypot(rawX, rawY) <= 5) return;
        d.moved = true;
        el.style.transition = "none";
        document.body.style.userSelect = "none";
        window.getSelection()?.removeAllRanges();
      }
      d.dx = rawX;
      // Nothing happens downwards, so dragging down meets rising resistance.
      d.dy = rawY > 0 ? rawY * 0.25 : rawY;
      d.trail.push({ t: performance.now(), x: ev.clientX, y: ev.clientY });
      if (d.trail.length > 8) d.trail.shift();
      const rot = reduceMotion ? 0 : d.dx * 0.05;
      el.style.transform = `translate(${d.dx}px, ${d.dy}px) rotate(${rot}deg)`;
      const horizontal = Math.abs(d.dx) >= Math.abs(d.dy);
      setStamps(
        horizontal ? Math.max(0, Math.min(1, d.dx / DISTANCE)) : 0,
        horizontal ? Math.max(0, Math.min(1, -d.dx / DISTANCE)) : 0,
        horizontal ? 0 : Math.max(0, Math.min(1, -d.dy / DISTANCE)),
      );
    };

    const up = (ev: PointerEvent) => {
      if (ev.pointerId !== d.pointerId) return;
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      window.removeEventListener("pointercancel", up);
      drag.current = null;
      document.body.style.userSelect = "";
      suppressClick.current = d.moved;
      if (!d.moved) return;
      release(el, d);
    };

    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    window.addEventListener("pointercancel", up);
  }

  function release(el: HTMLDivElement, d: DragState) {
    // Release velocity from the last ~100ms of movement, not the whole drag.
    const now = performance.now();
    const recent = d.trail.filter((p) => now - p.t < 100);
    const first = recent[0] ?? d.trail[0];
    const last = d.trail[d.trail.length - 1];
    const dt = Math.max(1, last.t - first.t);
    const vx = (last.x - first.x) / dt;
    const vy = (last.y - first.y) / dt;

    const decision = decisionFor(d.dx, d.dy, vx, vy);
    if (decision) {
      fly(decision, d.dx, d.dy, vx, vy);
      return;
    }
    // Not far or fast enough: settle back with a spring that keeps the
    // release velocity, so a half-hearted flick doesn't just stop dead.
    const from = el.style.transform || "none";
    const dist = Math.hypot(d.dx, d.dy) || 1;
    const towardCenter = (-(vx * d.dx + vy * d.dy) / dist) * 1000; // px/s
    const spring = springEasing({ duration: 0.45, bounce: 0.22, velocity: Math.max(-8, Math.min(8, towardCenter / dist)) });
    el.style.transform = "";
    el.style.transition = "";
    setStamps(0, 0, 0);
    if (!reduceMotion && dist > 2) {
      el.animate([{ transform: from }, { transform: "none" }], { duration: spring.duration, easing: spring.easing });
    }
  }

  return (
    <div className="deck">
      {cards
        .slice(0, 3)
        .map((c, depth) => (
          <div
            key={c.id}
            ref={depth === 0 ? topRef : undefined}
            className="deck-card"
            data-depth={depth}
            style={depth === 0 ? { touchAction: "none" } : undefined}
            aria-hidden={depth !== 0}
            onPointerDown={depth === 0 ? onPointerDown : undefined}
            onClickCapture={(e) => {
              if (suppressClick.current) {
                e.preventDefault();
                e.stopPropagation();
                suppressClick.current = false;
              }
            }}
          >
            {depth === 0 && (
              <>
                <div className="stamp stamp-keep" ref={(el) => void (stamps.current.keep = el)}>Keep</div>
                <div className="stamp stamp-skip" ref={(el) => void (stamps.current.skip = el)}>Skip</div>
                <div className="stamp stamp-save" ref={(el) => void (stamps.current.save = el)}>Save</div>
              </>
            )}
            <CardFace cluster={c} onOpen={onOpen} />
          </div>
        ))
        .reverse()}
    </div>
  );
});

function CardFace({ cluster, onOpen }: { cluster: Cluster; onOpen: (s: Story) => void }) {
  const { topic, source } = useMeta();
  const lead = cluster.lead;
  const [imgOk, setImgOk] = useState(true);
  const thread = cluster.discussions.find((d) => d.source === "hn") ?? cluster.discussions[0];
  return (
    <>
      {lead.image && imgOk ? (
        <div className="deck-media">
          <img src={lead.image} alt="" draggable={false} referrerPolicy="no-referrer" onError={() => setImgOk(false)} />
        </div>
      ) : (
        <div className="deck-media placeholder">{source(lead.source).name}</div>
      )}
      <div className="deck-body">
        <div className="story-top" style={{ marginBottom: 0 }}>
          <SourceMark id={lead.source} />
          <span className="dot">·</span>
          <span className="mono">{timeAgo(lead.published_at)}</span>
          {cluster.topics.slice(0, 2).map((t) => (
            <span key={t} className="tag" style={{ cursor: "default" }}>
              {topic(t)?.label}
            </span>
          ))}
        </div>
        <h2 className="deck-title">
          <a href={lead.url} target="_blank" rel="noreferrer" draggable={false} onClick={() => onOpen(lead)}>
            {lead.title}
          </a>
        </h2>
        {lead.summary && <p className="deck-summary">{lead.summary}</p>}
        <div className="deck-foot">
          {cluster.source_count > 1 && (
            <span className="meta-item">
              <SourceStack ids={cluster.sources} />
              {cluster.source_count} sources
            </span>
          )}
          {thread && (
            <span className="meta-item">
              {thread.score != null && (
                <>
                  <ArrowUp size={13} aria-hidden />
                  {compact(thread.score)}
                </>
              )}
              <MessageSquare size={13} aria-hidden />
              {compact(thread.comments ?? 0)}
            </span>
          )}
          {cluster.reasons[0] && (
            <span className="meta-item" style={{ color: "var(--accent)" }}>
              <Sparkles size={13} aria-hidden />
              {cluster.reasons[0]}
            </span>
          )}
        </div>
      </div>
    </>
  );
}
