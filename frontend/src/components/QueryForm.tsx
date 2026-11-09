import { useState } from "react";
import type { FormEvent } from "react";

interface Props {
  loading: boolean;
  onSubmit: (query: string) => void;
}

const EXAMPLES: string[] = [
  "Find me a vegetarian biryani under ₹300 that can arrive within 30 minutes. I prefer highly rated restaurants.",
  "suggest a biryani",
  "Jain thali in Dadar under ₹300",
  "cheap veg momos in Powai asap",
  "Which biryani place is better in Bandra, under 350?",
];

export default function QueryForm({ loading, onSubmit }: Props) {
  const [value, setValue] = useState("");
  const empty = value.trim().length === 0;

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (empty || loading) return;
    onSubmit(value.trim());
  }

  function pick(example: string) {
    setValue(example);
    onSubmit(example);
  }

  return (
    <section className="card query-form">
      <form onSubmit={handleSubmit}>
        <label htmlFor="query-input" className="visually-hidden">
          What do you want to eat
        </label>
        <div className="query-row">
          <input
            id="query-input"
            type="text"
            value={value}
            maxLength={500}
            placeholder="e.g. veg biryani under ₹300 in 30 minutes"
            onChange={(event) => setValue(event.target.value)}
            autoComplete="off"
          />
          <button type="submit" disabled={empty || loading}>
            Decide
          </button>
        </div>
      </form>
      <ul className="chips" aria-label="Example requests">
        {EXAMPLES.map((example) => (
          <li key={example}>
            <button type="button" className="chip" onClick={() => pick(example)}>
              {example}
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
