import { useState } from "react";
import type { FormEvent } from "react";
import type { RefineAction } from "../types";

interface Props {
  hasPick: boolean;
  busy: boolean;
  error: string | null;
  onAction: (action: RefineAction, label: string) => void;
  onText: (text: string) => void;
}

const ACTIONS: Array<{ action: RefineAction; label: string }> = [
  { action: "cheaper", label: "Cheaper" },
  { action: "faster", label: "Faster" },
  { action: "better_rated", label: "Better rated" },
];

export default function RefineRow({ hasPick, busy, error, onAction, onText }: Props) {
  const [text, setText] = useState("");
  const empty = text.trim().length === 0;

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (empty || busy) return;
    onText(text.trim());
    setText("");
  }

  return (
    <section className="card refine" aria-labelledby="refine-heading">
      <h2 id="refine-heading" className="section-title">
        Refine
      </h2>
      <ul className="chips">
        {ACTIONS.map((item) => (
          <li key={item.action}>
            <button
              type="button"
              className="chip"
              disabled={!hasPick || busy}
              onClick={() => onAction(item.action, item.label)}
            >
              {item.label}
            </button>
          </li>
        ))}
      </ul>
      <form className="query-row" onSubmit={submit}>
        <label htmlFor="refine-input" className="visually-hidden">
          Change something about this request
        </label>
        <input
          id="refine-input"
          type="text"
          value={text}
          maxLength={200}
          placeholder="Change something… e.g. make it vegan"
          autoComplete="off"
          onChange={(event) => setText(event.target.value)}
        />
        <button type="submit" disabled={empty || busy}>
          Refine
        </button>
      </form>
      {busy ? <p className="muted">Refining…</p> : null}
      {error ? (
        <p className="error-text" role="alert">
          {error}
        </p>
      ) : null}
    </section>
  );
}
