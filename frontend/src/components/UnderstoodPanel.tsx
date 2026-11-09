import type { ParsedRequest, Span } from "../types";
import { rupeesInr } from "../format";
import { fieldLabel } from "../fields";

interface Props {
  query: string;
  parsed: ParsedRequest;
  busy?: boolean;
  onDrop?: (field: string) => void;
}

interface Row {
  label: string;
  fields: string[];
  drop: string;
  value: string | null;
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

function tagFor(parsed: ParsedRequest, row: Row): "kept" | "changed" | null {
  if (parsed.refined_from === null || row.value === null) return null;
  if (row.fields.some((field) => parsed.adjusted.includes(field))) return "changed";
  if (row.fields.some((field) => parsed.carried_over.includes(field))) return "kept";
  return null;
}

export default function UnderstoodPanel({ query, parsed, busy = false, onDrop }: Props) {
  const segments = buildSegments(query, parsed.spans);
  const ratingField = parsed.min_rating !== null ? "min_rating" : "rating_preference";
  const rows: Row[] = [
    { label: "Dish", fields: ["dish"], drop: "dish", value: parsed.dish },
    { label: "Cuisine", fields: ["cuisine"], drop: "cuisine", value: parsed.cuisine },
    { label: "Ingredients", fields: ["ingredients"], drop: "ingredients", value: joined(parsed.ingredients) },
    { label: "Diet", fields: ["diet"], drop: "diet", value: dietValue(parsed) },
    {
      label: "Budget",
      fields: ["budget"],
      drop: "budget",
      value: parsed.max_price_inr === null ? null : `Up to ${rupeesInr(parsed.max_price_inr)}`,
    },
    {
      label: "Delivery",
      fields: ["delivery_time"],
      drop: "delivery_time",
      value: parsed.max_eta_min === null ? null : `Within ${parsed.max_eta_min} min`,
    },
    { label: "Rating", fields: ["min_rating", "rating_preference"], drop: ratingField, value: ratingValue(parsed) },
    { label: "Location", fields: ["location"], drop: "location", value: parsed.location },
    {
      label: "Price preference",
      fields: ["price_preference"],
      drop: "price_preference",
      value: parsed.price_preference === "low" ? "Prefers lower price" : null,
    },
    {
      label: "Speed preference",
      fields: ["speed_preference"],
      drop: "speed_preference",
      value: parsed.speed_preference === "fast" ? "Prefers fast delivery" : null,
    },
    { label: "Other", fields: ["other_preferences"], drop: "other_preferences", value: joined(parsed.other_preferences) },
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
        {rows.map((row) => {
          const tag = tagFor(parsed, row);
          return (
            <div key={row.label} className="grid-item">
              <dt>{row.label}</dt>
              <dd className={row.value === null ? "muted" : "value-line"}>
                <span>{row.value ?? "not specified"}</span>
                {tag ? <span className={`tag tag-${tag}`}>{tag}</span> : null}
                {row.value !== null && onDrop ? (
                  <button
                    type="button"
                    className="drop-btn"
                    aria-label={`Remove ${fieldLabel(row.drop)}`}
                    title={`Remove ${fieldLabel(row.drop)}`}
                    disabled={busy}
                    onClick={() => onDrop(row.drop)}
                  >
                    ×
                  </button>
                ) : null}
              </dd>
            </div>
          );
        })}
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
