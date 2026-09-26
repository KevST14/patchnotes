import { useId, useLayoutEffect, useMemo, useRef, useState } from "react";

/**
 * Two tiny chart forms, both single-series (so: one accent colour, no
 * legend — the surrounding label names the series):
 *
 * - Sparkline: 2px line + 10% area wash + end dot with a surface ring.
 *   Hover/drag shows a crosshair snapped to the nearest bucket.
 * - SparkBars: columns <= 24px, 4px rounded tops, 2px gaps, one baseline.
 *   Each bar is its own hover target.
 *
 * Values are always also printed nearby (counts in the table/tile), so the
 * tooltip enhances rather than gates.
 */

interface BucketProps {
  values: number[];
  /** Unix seconds at the end of the last bucket (usually "now"). */
  endTs: number;
  bucketSeconds: number;
  unit?: [string, string];
}

function bucketLabel(i: number, n: number, endTs: number, bucketSeconds: number): string {
  const start = new Date((endTs - bucketSeconds * (n - i)) * 1000);
  const end = new Date((endTs - bucketSeconds * (n - i - 1)) * 1000);
  if (bucketSeconds < 86400) {
    const day = start.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" });
    const t = (d: Date) => d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
    return `${day}, ${t(start)}–${t(end)}`;
  }
  const d = (x: Date) => x.toLocaleDateString(undefined, { day: "numeric", month: "short" });
  return `${d(start)} – ${d(end)}`;
}

interface Tip {
  x: number;
  y: number;
  index: number;
}

function Tooltip({ tip, values, endTs, bucketSeconds, unit }: BucketProps & { tip: Tip }) {
  const v = values[tip.index];
  const [one, many] = unit ?? ["story", "stories"];
  return (
    <div className="chart-tip" style={{ left: tip.x, top: tip.y }} role="presentation">
      <b>{v.toLocaleString()}</b> {v === 1 ? one : many}
      <br />
      <span>{bucketLabel(tip.index, values.length, endTs, bucketSeconds)}</span>
    </div>
  );
}

export function Sparkline({
  values,
  endTs,
  bucketSeconds,
  unit,
  width = 96,
  height = 28,
  label,
}: BucketProps & { width?: number; height?: number; label: string }) {
  const gradId = useId();
  const [tip, setTip] = useState<Tip | null>(null);
  const pad = 4; // room for the end dot and its ring
  const max = Math.max(1, ...values);
  const n = values.length;

  const points = useMemo(
    () =>
      values.map((v, i) => [
        pad + (i * (width - pad * 2)) / Math.max(1, n - 1),
        height - pad - (v / max) * (height - pad * 2),
      ]),
    [values, width, height, max, n],
  );

  const line = points.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join("");
  const area = `${line}L${points[n - 1][0].toFixed(1)},${height - pad}L${points[0][0].toFixed(1)},${height - pad}Z`;
  const [lx, ly] = points[n - 1];

  function onMove(e: React.PointerEvent<SVGSVGElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    const rel = ((e.clientX - rect.left) / rect.width) * width;
    const index = Math.round(((rel - pad) / (width - pad * 2)) * (n - 1));
    const i = Math.max(0, Math.min(n - 1, index));
    const [px, py] = points[i];
    setTip({ index: i, x: rect.left + (px / width) * rect.width, y: rect.top + (py / height) * rect.height });
  }

  const hovered = tip ? points[tip.index] : null;

  return (
    <>
      <svg
        className="spark"
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={`${label}: ${values.join(", ")}`}
        onPointerMove={onMove}
        onPointerLeave={() => setTip(null)}
      >
        <defs>
          <linearGradient id={gradId} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0" stopColor="var(--chart-series)" stopOpacity="0.16" />
            <stop offset="1" stopColor="var(--chart-series)" stopOpacity="0.02" />
          </linearGradient>
        </defs>
        <line x1={pad} x2={width - pad} y1={height - pad} y2={height - pad} stroke="var(--chart-grid)" strokeWidth="1" />
        <path d={area} fill={`url(#${gradId})`} />
        <path d={line} fill="none" stroke="var(--chart-series)" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
        {hovered && (
          <line x1={hovered[0]} x2={hovered[0]} y1={1} y2={height - pad} stroke="var(--muted)" strokeWidth="1" />
        )}
        <circle
          cx={hovered ? hovered[0] : lx}
          cy={hovered ? hovered[1] : ly}
          r="4"
          fill="var(--chart-series)"
          stroke="var(--surface)"
          strokeWidth="2"
        />
        {/* transparent hit area, bigger than the line */}
        <rect x="0" y="0" width={width} height={height} fill="transparent" />
      </svg>
      {tip && <Tooltip tip={tip} values={values} endTs={endTs} bucketSeconds={bucketSeconds} unit={unit} />}
    </>
  );
}

export function SparkBars({
  values,
  endTs,
  bucketSeconds,
  unit,
  height = 44,
  label,
}: BucketProps & { height?: number; label: string }) {
  const [tip, setTip] = useState<Tip | null>(null);
  const [width, setWidth] = useState(0);
  const ref = useRef<HTMLDivElement>(null);

  // Lay bars out in real pixels so the rounded tops stay round at any width.
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    ro.observe(el);
    setWidth(el.getBoundingClientRect().width);
    return () => ro.disconnect();
  }, []);

  const max = Math.max(1, ...values);
  const n = values.length;
  const gap = 2;
  const slot = width > 0 ? (width + gap) / n : 0;
  const barW = Math.max(1, Math.min(24, slot - gap));

  return (
    <div ref={ref} style={{ width: "100%" }}>
      {width > 0 && (
        <svg
          className="spark"
          width={width}
          height={height}
          viewBox={`0 0 ${width} ${height}`}
          role="img"
          aria-label={`${label}: ${values.join(", ")}`}
          onPointerLeave={() => setTip(null)}
        >
          {values.map((v, i) => {
            const h = v === 0 ? 0 : Math.max(3, (v / max) * (height - 2));
            const x = i * slot + (slot - gap - barW) / 2;
            const y = height - 1 - h;
            const r = Math.min(4, h / 2, barW / 2);
            const d =
              h === 0
                ? ""
                : `M${x},${height - 1}V${y + r}Q${x},${y} ${x + r},${y}H${x + barW - r}Q${x + barW},${y} ${x + barW},${y + r}V${height - 1}Z`;
            return (
              <g key={i}>
                {d && (
                  <path
                    d={d}
                    fill={i === n - 1 ? "var(--chart-series)" : "var(--chart-muted)"}
                    opacity={tip && tip.index !== i ? 0.55 : 1}
                  />
                )}
                <rect
                  x={i * slot - gap / 2}
                  y={0}
                  width={slot}
                  height={height}
                  fill="transparent"
                  onPointerEnter={(e) => {
                    const rect = (e.currentTarget.ownerSVGElement as SVGSVGElement).getBoundingClientRect();
                    setTip({ index: i, x: rect.left + x + barW / 2, y: rect.top + Math.min(y, height - 4) });
                  }}
                />
              </g>
            );
          })}
          <line x1="0" x2={width} y1={height - 0.5} y2={height - 0.5} stroke="var(--chart-grid)" strokeWidth="1" />
        </svg>
      )}
      {tip && <Tooltip tip={tip} values={values} endTs={endTs} bucketSeconds={bucketSeconds} unit={unit} />}
    </div>
  );
}
