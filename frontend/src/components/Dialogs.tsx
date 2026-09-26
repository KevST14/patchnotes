import { useEffect, useRef, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { Check, Moon, Monitor, Plus, Sun, X } from "lucide-react";
import { api } from "../api";
import { useMeta, type ThemeChoice } from "../hooks";
import type { Prefs } from "../types";

/** Native <dialog>: focus trapping, Esc and the backdrop come for free. */
function Modal({ open, onClose, title, children }: { open: boolean; onClose: () => void; title: string; children: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (open && !el.open) el.showModal();
    if (!open && el.open) el.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      className="modal"
      onClose={onClose}
      onClick={(e) => {
        if (e.target === ref.current) onClose(); // click on the backdrop
      }}
      aria-label={title}
    >
      <div className="modal-head">
        <h2>{title}</h2>
        <button type="button" className="icon-btn" onClick={onClose} aria-label="Close">
          <X size={18} />
        </button>
      </div>
      <div className="modal-body">{children}</div>
    </dialog>
  );
}

const SHORTCUTS: { group: string; items: [string[], string][] }[] = [
  {
    group: "Anywhere",
    items: [
      [["g", "t"], "Today"],
      [["g", "c"], "Catch up"],
      [["g", "r"], "Trend radar"],
      [["g", "q"], "Quiz"],
      [["g", "s"], "Saved"],
      [["r"], "Fetch new stories now"],
      [[","], "Settings"],
      [["?"], "This list"],
    ],
  },
  {
    group: "Today",
    items: [
      [["j"], "Next story"],
      [["k"], "Previous story"],
      [["o"], "Open story"],
      [["s"], "Save / unsave"],
      [["x"], "Not interested"],
      [["e"], "Compare coverage"],
      [["c"], "Top comments"],
      [["/"], "Search"],
      [["f", "·", "t", "·", "l"], "For you · Top · Latest"],
    ],
  },
  {
    group: "Catch up",
    items: [
      [["→"], "Keep"],
      [["←"], "Skip"],
      [["↑"], "Save"],
      [["space"], "Open"],
      [["z"], "Undo"],
    ],
  },
  {
    group: "Quiz",
    items: [
      [["1", "–", "4"], "Answer"],
      [["enter"], "Next question"],
    ],
  },
];

export function ShortcutsDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  return (
    <Modal open={open} onClose={onClose} title="Keyboard shortcuts">
      {SHORTCUTS.map((g) => (
        <div className="shortcut-group" key={g.group}>
          <h3>{g.group}</h3>
          {g.items.map(([keys, label]) => (
            <div className="shortcut" key={label}>
              <span>{label}</span>
              <span className="keys">
                {keys.map((k, i) => (k === "·" || k === "–" ? <span key={i} className="muted">{k === "·" ? "/" : "–"}</span> : <kbd key={i}>{k}</kbd>))}
              </span>
            </div>
          ))}
        </div>
      ))}
    </Modal>
  );
}

export function SettingsDialog({
  open,
  onClose,
  theme,
  setTheme,
}: {
  open: boolean;
  onClose: () => void;
  theme: ThemeChoice;
  setTheme: (t: ThemeChoice) => void;
}) {
  const { meta } = useMeta();
  const [prefs, setPrefs] = useState<Prefs | null>(null);
  const [term, setTerm] = useState("");

  useEffect(() => {
    if (open) api.prefs().then(setPrefs).catch((e: Error) => toast.error(e.message));
  }, [open]);

  const update = async (patch: Partial<Prefs>) => {
    if (!prefs) return;
    setPrefs({ ...prefs, ...patch });
    try {
      setPrefs(await api.setPrefs(patch));
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  const toggle = (list: string[], id: string) => (list.includes(id) ? list.filter((x) => x !== id) : [...list, id]);

  return (
    <Modal open={open} onClose={onClose} title="Settings">
      <div className="field">
        <span className="label">Theme</span>
        <div className="seg" role="group" aria-label="Theme">
          {(
            [
              ["light", "Light", Sun],
              ["dark", "Dark", Moon],
              ["system", "System", Monitor],
            ] as const
          ).map(([id, label, Icon]) => (
            <button key={id} type="button" aria-pressed={theme === id} onClick={() => setTheme(id)}>
              <Icon size={14} aria-hidden /> {label}
            </button>
          ))}
        </div>
      </div>

      <div className="field">
        <span className="label">Topics you follow</span>
        <p className="hint">These always get a boost in For You, on top of what it learns from you.</p>
        <div className="chips">
          {meta.topics.map((t) => {
            const on = prefs?.followed_topics.includes(t.id) ?? false;
            return (
              <button key={t.id} type="button" className="chip" aria-pressed={on} disabled={!prefs} onClick={() => prefs && update({ followed_topics: toggle(prefs.followed_topics, t.id) })}>
                {on && <Check size={13} aria-hidden />}
                {t.label}
              </button>
            );
          })}
        </div>
      </div>

      <div className="field">
        <label htmlFor="mute-term">Muted words</label>
        <p className="hint">Stories whose headline contains one of these (as a whole word) are hidden everywhere.</p>
        <form
          className="input-row"
          onSubmit={(e) => {
            e.preventDefault();
            if (!prefs || !term.trim()) return;
            update({ muted_terms: [...prefs.muted_terms, term.trim()] });
            setTerm("");
          }}
        >
          <input id="mute-term" className="input" placeholder="e.g. crypto, Musk, deals" value={term} onChange={(e) => setTerm(e.target.value)} />
          <button type="submit" className="btn" disabled={!term.trim()}>
            <Plus size={15} aria-hidden /> Mute
          </button>
        </form>
        {prefs && prefs.muted_terms.length > 0 && (
          <div className="chips" style={{ marginTop: 10 }}>
            {prefs.muted_terms.map((t) => (
              <button key={t} type="button" className="chip" onClick={() => update({ muted_terms: prefs.muted_terms.filter((x) => x !== t) })} aria-label={`Unmute ${t}`}>
                {t}
                <X size={13} className="x" aria-hidden />
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="field" style={{ marginBottom: 0 }}>
        <span className="label">Sources</span>
        <p className="hint">Switch off a source to drop its stories from your feed (a story still shows if another source covered it too).</p>
        <div className="chips">
          {meta.sources.map((s) => {
            const muted = prefs?.muted_sources.includes(s.id) ?? false;
            return (
              <button
                key={s.id}
                type="button"
                className="chip"
                aria-pressed={!muted}
                disabled={!prefs}
                onClick={() => prefs && update({ muted_sources: toggle(prefs.muted_sources, s.id) })}
              >
                {!muted && <Check size={13} aria-hidden />}
                {s.name}
              </button>
            );
          })}
        </div>
      </div>
    </Modal>
  );
}
