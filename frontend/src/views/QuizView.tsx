import { Fragment, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { ArrowRight, Brain, Check, ExternalLink, RotateCcw, Trophy, X } from "lucide-react";
import { api } from "../api";
import { Empty, Skeleton, SourceMark } from "../components/Bits";
import { useAsync, useHashRoute, useHotkeys } from "../hooks";
import type { QuizQuestion } from "../types";
import { ago, timeAgo } from "../utils";

type Phase = "intro" | "playing" | "done";

const KIND_LABEL: Record<QuizQuestion["type"], string> = {
  blank: "Fill the blank",
  outlet: "Who wrote it",
  hn: "Hacker News",
  coverage: "Coverage",
};

function verdictLine(score: number, total: number) {
  const pct = score / total;
  if (pct === 1) return "Flawless. You actually read the news.";
  if (pct >= 0.75) return "Sharp. Most of it stuck.";
  if (pct >= 0.5) return "Not bad — a few slipped past.";
  if (pct > 0) return "The week got away from you. Catch-up mode helps.";
  return "Clean sweep, the wrong way. Time for a catch-up?";
}

export function QuizView() {
  const { params, replaceParams, navigate } = useHashRoute();
  const round = Math.max(1, Number(params.get("round") ?? 1) || 1);
  const quiz = useAsync(() => api.quiz(round), [round]);
  const history = useAsync(() => api.quizResults(), []);

  const [phase, setPhase] = useState<Phase>("intro");
  const [current, setCurrent] = useState(0);
  const [answers, setAnswers] = useState<(number | null)[]>([]);

  useEffect(() => {
    setPhase("intro");
    setCurrent(0);
    setAnswers([]);
  }, [quiz.data?.id]);

  const questions = quiz.data?.questions ?? [];
  const q = questions[current];
  const picked = answers[current] ?? null;
  const score = answers.reduce<number>((acc, a, i) => acc + (a !== null && a === questions[i]?.answer ? 1 : 0), 0);

  const start = () => {
    setAnswers(questions.map(() => null));
    setCurrent(0);
    setPhase("playing");
  };

  const choose = (i: number) => {
    if (phase !== "playing" || !q || picked !== null || i >= q.options.length) return;
    setAnswers((prev) => prev.map((a, idx) => (idx === current ? i : a)));
  };

  const next = async () => {
    if (picked === null) return;
    if (current + 1 < questions.length) {
      setCurrent((c) => c + 1);
      return;
    }
    setPhase("done");
    try {
      await api.addQuizResult(quiz.data!.id, score, questions.length);
      history.reload();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  useHotkeys({
    "1": () => choose(0),
    "2": () => choose(1),
    "3": () => choose(2),
    "4": () => choose(3),
    Enter: () => (phase === "intro" ? questions.length && start() : phase === "playing" ? next() : undefined),
    ArrowRight: () => phase === "playing" && next(),
  });

  return (
    <div className="quiz">
      <div className="page-head">
        <div>
          <h1 className="page-title">This week's quiz</h1>
          <p className="page-sub">Built from the last seven days of headlines. Stories you opened or kept come up more often.</p>
        </div>
      </div>

      {quiz.error && (
        <div className="banner" data-tone="error">
          {quiz.error}
        </div>
      )}
      {!quiz.data && quiz.loading && <Skeleton rows={3} />}

      {quiz.data && questions.length < 4 && (
        <Empty icon={<Brain size={22} />} title="Not enough news yet">
          The quiz needs a few days of stories to work with. Leave Patch Notes running and come back later.
        </Empty>
      )}

      {quiz.data && questions.length >= 4 && phase === "intro" && (
        <div className="quiz-card">
          <div className="quiz-kicker">
            <span>Round {round}</span>
            <span>{questions.length} questions</span>
          </div>
          <h2 className="quiz-headline">How much of this week's tech news stuck?</h2>
          <p className="muted" style={{ marginTop: -8 }}>
            Fill in missing names and numbers, pick which outlet wrote a headline, and guess which stories the internet cared about most. Answer with{" "}
            <kbd>1</kbd>–<kbd>4</kbd>, move on with <kbd>enter</kbd>.
          </p>
          <div className="quiz-actions" style={{ justifyContent: "space-between", alignItems: "center" }}>
            <History results={history.data ?? []} />
            <button type="button" className="btn btn-accent" onClick={start}>
              Start <ArrowRight size={15} aria-hidden />
            </button>
          </div>
        </div>
      )}

      {phase === "playing" && q && (
        <div className="quiz-card" key={q.id} style={{ animation: "rise 250ms var(--ease-out)" }}>
          <div className="quiz-progress" aria-hidden>
            {questions.map((qq, i) => (
              <i
                key={qq.id}
                data-state={
                  answers[i] === null || answers[i] === undefined
                    ? i === current
                      ? "current"
                      : undefined
                    : answers[i] === qq.answer
                      ? "right"
                      : "wrong"
                }
              />
            ))}
          </div>
          <div className="quiz-kicker">
            <span>
              {current + 1} / {questions.length} · {KIND_LABEL[q.type]}
            </span>
            {q.seen && <span title="You opened or kept this story">you read this one</span>}
          </div>
          <QuestionBody q={q} picked={picked} />
          <div className="options" data-layout={q.type === "blank" || q.type === "outlet" ? "grid" : "list"}>
            {q.options.map((opt, i) => {
              const state =
                picked === null ? undefined : i === q.answer ? "right" : i === picked ? "wrong" : "dim";
              return (
                <button type="button" key={opt + i} className="option" data-state={state} disabled={picked !== null} onClick={() => choose(i)}>
                  <kbd>{i + 1}</kbd>
                  <span>{opt}</span>
                  {q.option_values && <span className="value">{q.option_values[i]}</span>}
                  {state === "right" && <Check size={17} style={{ marginLeft: q.option_values ? 8 : "auto", color: "var(--keep)", flex: "none" }} />}
                  {state === "wrong" && <X size={17} style={{ marginLeft: q.option_values ? 8 : "auto", color: "var(--skip)", flex: "none" }} />}
                </button>
              );
            })}
          </div>
          {picked !== null && (
            <div className="reveal">
              <div>
                <div className="verdict" data-right={picked === q.answer}>
                  {picked === q.answer ? "Right." : `Not quite — it was ${q.options[q.answer]}.`}
                </div>
                <div className="muted">{q.explanation}</div>
              </div>
              <a href={q.story.url} target="_blank" rel="noreferrer" style={{ whiteSpace: "nowrap", display: "inline-flex", gap: 5, alignItems: "center" }}>
                Read it <ExternalLink size={13} aria-hidden />
              </a>
            </div>
          )}
          <div className="quiz-actions">
            <button type="button" className="btn btn-primary" disabled={picked === null} onClick={next}>
              {current + 1 < questions.length ? "Next" : "See score"} <ArrowRight size={15} aria-hidden />
            </button>
          </div>
        </div>
      )}

      {phase === "done" && quiz.data && (
        <div className="quiz-card" style={{ animation: "rise 250ms var(--ease-out)" }}>
          <div className="quiz-kicker">
            <span>Round {round} · done</span>
            <Trophy size={16} aria-hidden />
          </div>
          <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 20, margin: "16px 0 6px", flexWrap: "wrap" }}>
            <div>
              <div className="score-hero">
                {score}
                <small>/{questions.length}</small>
              </div>
              <p style={{ margin: "8px 0 0", fontSize: 17 }}>{verdictLine(score, questions.length)}</p>
            </div>
            <History results={history.data ?? []} />
          </div>
          <h3 className="section-title" style={{ marginTop: 24 }}>
            Review
          </h3>
          <div>
            {questions.map((qq, i) => (
              <ReviewRow key={qq.id} q={qq} answer={answers[i]} />
            ))}
          </div>
          <div className="quiz-actions">
            <button type="button" className="btn" onClick={() => navigate("catchup")}>
              Catch up on the news
            </button>
            <button type="button" className="btn btn-accent" onClick={() => replaceParams({ round: String(round + 1) })}>
              <RotateCcw size={15} aria-hidden /> New round
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function QuestionBody({ q, picked }: { q: QuizQuestion; picked: number | null }) {
  if (q.type === "blank" && q.headline) {
    const [before, after] = q.headline.split("_____");
    return (
      <h2 className="quiz-headline">
        {before}
        <span className="blank" data-filled={picked !== null}>
          {picked !== null ? q.options[q.answer] : " "}
        </span>
        {after}
      </h2>
    );
  }
  if (q.type === "outlet" && q.headline) {
    return (
      <>
        <p className="muted" style={{ margin: "14px 0 0" }}>{q.prompt}</p>
        <h2 className="quiz-headline" style={{ marginTop: 6 }}>“{q.headline}”</h2>
      </>
    );
  }
  return <h2 className="quiz-headline">{q.prompt}</h2>;
}

function ReviewRow({ q, answer }: { q: QuizQuestion; answer: number | null | undefined }) {
  const right = answer === q.answer;
  return (
    <a className="mini-story" href={q.story.url} target="_blank" rel="noreferrer">
      <div className="t" style={{ display: "flex", gap: 10 }}>
        {right ? (
          <Check size={17} style={{ color: "var(--keep)", flex: "none", marginTop: 3 }} aria-label="Right" />
        ) : (
          <X size={17} style={{ color: "var(--skip)", flex: "none", marginTop: 3 }} aria-label="Wrong" />
        )}
        <span>{q.story.title}</span>
      </div>
      <div className="m" style={{ paddingLeft: 27 }}>
        <SourceMark id={q.story.source} />
        <span>{timeAgo(q.story.published_at)}</span>
      </div>
    </a>
  );
}

function History({ results }: { results: { id: number; score: number; total: number; taken_at: number }[] }) {
  const recent = useMemo(() => [...results].reverse().slice(-12), [results]);
  if (recent.length === 0) return <span className="muted" style={{ fontSize: 13 }}>Your scores will show up here.</span>;
  const best = Math.max(...recent.map((r) => r.score / r.total));
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6, minWidth: 160 }}>
      <div className="history" role="img" aria-label={`Recent scores: ${recent.map((r) => `${r.score}/${r.total}`).join(", ")}`}>
        {recent.map((r, i) => (
          <Fragment key={r.id}>
            <span
              className="history-bar"
              title={`${r.score}/${r.total} · ${ago(r.taken_at)}`}
              style={{
                height: `${Math.max(6, (r.score / r.total) * 100)}%`,
                opacity: i === recent.length - 1 ? 1 : 0.45,
              }}
            />
          </Fragment>
        ))}
      </div>
      <span className="mono muted" style={{ fontSize: 11 }}>
        last {recent.length} · best {Math.round(best * 100)}%
      </span>
    </div>
  );
}
