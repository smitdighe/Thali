import { useState } from "react";
import type { FormEvent, KeyboardEvent, RefObject } from "react";
import VoiceButton from "./VoiceButton";

interface Props {
  value: string;
  lastQuery: string;
  loading: boolean;
  inputRef: RefObject<HTMLInputElement | null>;
  onChange: (value: string) => void;
  onSubmit: (query: string) => void;
}

export default function QueryForm({ value, lastQuery, loading, inputRef, onChange, onSubmit }: Props) {
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const empty = value.trim().length === 0;

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (empty || loading) return;
    onSubmit(value.trim());
  }

  function handleKey(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Escape") {
      onChange("");
    } else if (event.key === "ArrowUp" && value.length === 0 && lastQuery.length > 0) {
      event.preventDefault();
      onChange(lastQuery);
    }
  }

  return (
    <form className="query-form" onSubmit={handleSubmit}>
      <label htmlFor="query-input" className="visually-hidden">
        What do you want to eat
      </label>
      <div className="query-row">
        <input
          id="query-input"
          ref={inputRef}
          type="text"
          value={value}
          maxLength={500}
          placeholder="e.g. veg biryani under ₹300 in 30 minutes"
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={handleKey}
          autoComplete="off"
        />
        <VoiceButton
          disabled={loading}
          onInterim={onChange}
          onFinal={(text) => {
            onChange(text);
            onSubmit(text);
          }}
          onError={setVoiceError}
        />
        <button type="submit" disabled={empty || loading}>
          Decide
        </button>
      </div>
      {voiceError ? (
        <p className="error-text" role="alert">
          {voiceError}
        </p>
      ) : null}
    </form>
  );
}
