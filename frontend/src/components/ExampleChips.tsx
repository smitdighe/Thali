interface Props {
  collapsed: boolean;
  onPick: (example: string) => void;
}

const EXAMPLES: string[] = [
  "Find me a vegetarian biryani under ₹300 that can arrive within 30 minutes. I prefer highly rated restaurants.",
  "suggest a biryani",
  "veg biryani 300 ke andar, 30 min mein",
  "cheap veg momos in Powai asap",
  "Jain thali in Dadar under ₹300",
];

export default function ExampleChips({ collapsed, onPick }: Props) {
  const list = (
    <ul className="chips" aria-label="Example requests">
      {EXAMPLES.map((example) => (
        <li key={example}>
          <button type="button" className="chip" onClick={() => onPick(example)}>
            {example}
          </button>
        </li>
      ))}
    </ul>
  );
  if (!collapsed) return list;
  return (
    <details className="examples">
      <summary>Example requests</summary>
      {list}
    </details>
  );
}
