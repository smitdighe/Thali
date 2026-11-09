import type { ParsedRequest, Span } from "../types";
import { rupeesInr } from "../format";

interface Props {
  query: string;
  parsed: ParsedRequest;
}

interface Segment {
  text: string;
  span: Span | null;
}

function buildSegments(query: string, spans: Span[]): Segment[] {
  const chars = Array.from(query);
  const ordered = [...spans].sort((a, b) => a.start - b.start);
  const segments: Segment[] = [];
  let cursor = 0;
  for (const span of ordered) {
    if (span.start < cursor || span.end <= span.start || span.end > chars.length) continue;
    if (span.start > cursor) segments.push({ text: chars.slice(cursor, span.start).join(""), span: null });
    segments.push({ text: chars.slice(span.start, span.end).join(""), span });
    cursor = span.end;
  }
  if (cursor < chars.length) segments.push({ text: chars.slice(cursor).join(""), span: null });
  return segments;
}

function ratingValue(parsed: ParsedRequest): string | null {
  if (parsed.min_rating !== null) return `${parsed.min_rating.toFixed(1)}+`;
  if (parsed.rating_preference === "high") return "Prefers highly rated";
  return null;
}

function dietValue(parsed: ParsedRequest): string | null {
  if (parsed.diet === null) return null;
  return parsed.diet === "non_veg" ? "non-veg" : parsed.diet;
}

function fieldClass(field: string): string {
  return `mark field-${field.replace(/[^a-z_]/g, "")}`;
}

function joined(values: string[]): string | null {
  return values.length > 0 ? values.join(", ") : null;
}

export default function UnderstoodPanel({ query, parsed }: Props) {
  const segments = buildSegments(query, parsed.spans);
  const rows: Array<[string, string | null]> = [
    ["Dish", parsed.dish],
    ["Cuisine", parsed.cuisine],
    ["Ingredients", joined(parsed.ingredients)],
    ["Diet", dietValue(parsed)],
    ["Budget", parsed.max_price_inr === null ? null : `Up to ${rupeesInr(parsed.max_price_inr)}`],
    ["Delivery", parsed.max_eta_min === null ? null : `Within ${parsed.max_eta_min} min`],
    ["Rating", ratingValue(parsed)],
    ["Location", parsed.location],
    ["Price preference", parsed.price_preference === "low" ? "Prefers lower price" : null],
    ["Speed preference", parsed.speed_preference === "fast" ? "Prefers fast delivery" : null],
    ["Other", joined(parsed.other_preferences)],
  ];

  return (
    <section className="card" aria-labelledby="understood-heading">
      <div className="card-head">
        <h2 id="understood-heading" className="section-title">
          What you asked for
        </h2>
        <span className="badge">{parsed.parser === "llm" ? "read by LLM" : "read by rules"}</span>
      </div>
      <p className="query-text">
        {segments.map((segment, index) =>
          segment.span === null ? (
            <span key={index}>{segment.text}</span>
          ) : (
            <mark key={index} className={fieldClass(segment.span.field)} title={`${segment.span.field}: ${segment.span.text}`}>
              {segment.text}
            </mark>
          ),
        )}
      </p>
      <dl className="grid">
        {rows.map(([label, value]) => (
          <div key={label} className="grid-item">
            <dt>{label}</dt>
            <dd className={value === null ? "muted" : undefined}>{value ?? "not specified"}</dd>
          </div>
        ))}
      </dl>
      {parsed.missing.includes("food") ? (
        <p className="muted">No dish or cuisine given, so every dish is considered.</p>
      ) : null}
      {parsed.notes.length > 0 ? (
        <ul className="notes muted">
          {parsed.notes.map((note, index) => (
            <li key={index}>{note}</li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
