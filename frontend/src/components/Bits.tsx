import type { ReactNode } from "react";
import { useMeta } from "../hooks";

export function SourceMark({ id, long = false }: { id: string; long?: boolean }) {
  const { source } = useMeta();
  const s = source(id);
  return (
    <span className="source-mark" style={{ ["--src" as string]: s.color }}>
      <i aria-hidden />
      {long ? s.name : s.short}
    </span>
  );
}

export function SourceStack({ ids }: { ids: string[] }) {
  const { source } = useMeta();
  return (
    <span className="source-stack" aria-hidden>
      {ids.slice(0, 5).map((id) => (
        <i key={id} style={{ ["--src" as string]: source(id).color }} />
      ))}
    </span>
  );
}

export function TopicTag({ id, onClick }: { id: string; onClick?: (id: string) => void }) {
  const { topic } = useMeta();
  const t = topic(id);
  if (!t) return null;
  return (
    <button type="button" className="tag" onClick={() => onClick?.(id)} title={`Show only ${t.label}`}>
      {t.label}
    </button>
  );
}

export function Empty({
  icon,
  title,
  children,
  action,
}: {
  icon: ReactNode;
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="empty">
      <span className="icon-wrap">{icon}</span>
      <h3>{title}</h3>
      {children && <p>{children}</p>}
      {action}
    </div>
  );
}

export function Skeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => (
        <div className="skeleton" key={i}>
          <div style={{ width: "22%" }} />
          <div style={{ width: `${70 + ((i * 13) % 25)}%`, height: 18 }} />
          <div style={{ width: "55%" }} />
        </div>
      ))}
    </div>
  );
}
