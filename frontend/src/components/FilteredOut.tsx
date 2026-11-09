import type { OptionResult } from "../types";

interface Props {
  options: OptionResult[];
}

function providersOf(option: OptionResult): string {
  return option.listings.map((scored) => scored.listing.provider_label).join(", ");
}

export default function FilteredOut({ options }: Props) {
  return (
    <section aria-labelledby="filtered-heading">
      <h2 id="filtered-heading" className="section-title">
        Filtered out
      </h2>
      <details className="card">
        <summary>{options.length} options filtered out</summary>
        <ul className="filtered-list">
          {options.map((option) => (
            <li key={option.option_id}>
              {option.item} · {option.restaurant}
              {option.area ? ` (${option.area})` : ""} · {providersOf(option)}
              {option.best.violations.length > 0 ? ` — ${option.best.violations.join("; ")}` : ""}
            </li>
          ))}
        </ul>
      </details>
    </section>
  );
}
