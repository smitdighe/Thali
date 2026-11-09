import { useState } from "react";
import type { KeyboardEvent } from "react";
import type { OptionResult, ParsedRequest, Recommendation } from "../types";
import { etaText, ratingText, rupees, rupeesInr } from "../format";

interface Props {
  recommendation: Recommendation | null;
  ranked: OptionResult[];
  excluded: OptionResult[];
  parsed: ParsedRequest;
}

type Kind = "pick" | "ranked" | "excluded";

interface Point {
  option: OptionResult;
  kind: Kind;
  priceInr: number;
  rating: number;
  eta: number | null;
  x: number;
  y: number;
  r: number;
}

const WIDTH = 480;
const HEIGHT = 330;
const MARGIN = { left: 44, right: 14, top: 22, bottom: 44 };
const MIN_RADIUS = 4;
const MAX_RADIUS = 11;

function niceStep(span: number, target: number): number {
  const raw = span / target;
  const magnitude = Math.pow(10, Math.floor(Math.log10(raw)));
  const fraction = raw / magnitude;
  if (fraction <= 1) return magnitude;
  if (fraction <= 2) return 2 * magnitude;
  if (fraction <= 5) return 5 * magnitude;
  return 10 * magnitude;
}

function ticksBetween(min: number, max: number, step: number): number[] {
  const out: number[] = [];
  const first = Math.ceil(min / step) * step;
  for (let value = first; value <= max + step / 1000; value += step) out.push(Number(value.toFixed(4)));
  return out;
}

function bestPriceInr(option: OptionResult): number | null {
  const listing = option.best.listing;
  const paise = listing.effective_price_paise ?? listing.price_paise;
  return paise === null ? null : paise / 100;
}

function kindOf(option: OptionResult, pickId: string | null): Kind {
  if (option.option_id === pickId) return "pick";
  return option.feasible ? "ranked" : "excluded";
}

interface Raw {
  option: OptionResult;
  kind: Kind;
  priceInr: number;
  rating: number;
  eta: number | null;
}

function collect(options: OptionResult[], pickId: string | null): Raw[] {
  const out: Raw[] = [];
  for (const option of options) {
    const price = bestPriceInr(option);
    const rating = option.best.listing.rating;
    if (price === null || rating === null) continue;
    out.push({ option, kind: kindOf(option, pickId), priceInr: price, rating, eta: option.best.listing.eta_min_high });
  }
  return out;
}

function radiusFor(eta: number | null, minEta: number, maxEta: number): number {
  if (eta === null) return MIN_RADIUS;
  if (maxEta === minEta) return (MIN_RADIUS + MAX_RADIUS) / 2;
  const speed = 1 - (eta - minEta) / (maxEta - minEta);
  return MIN_RADIUS + 1 + speed * (MAX_RADIUS - MIN_RADIUS - 1);
}

function describe(option: OptionResult): string[] {
  const listing = option.best.listing;
  const place = option.area ? `${option.restaurant} (${option.area})` : option.restaurant;
  const lines = [
    `${option.item} · ${place}`,
    listing.provider_label,
    `${rupees(listing.effective_price_paise ?? listing.price_paise)} · ${ratingText(listing.rating, listing.rating_count)}`,
    `ETA ${etaText(listing.eta_min_low, listing.eta_min_high)}`,
  ];
  if (option.best.violations.length > 0) lines.push(option.best.violations[0] ?? "");
  if (option.why_not) lines.push(option.why_not);
  return lines.filter((line) => line.length > 0);
}

export default function TradeoffChart({ recommendation, ranked, excluded, parsed }: Props) {
  const [hover, setHover] = useState<string | null>(null);
  const [pinned, setPinned] = useState<string | null>(null);

  const pickId = recommendation ? recommendation.option.option_id : null;
  const all = [...ranked, ...excluded];
  const raws = collect(all, pickId);
  const notPlotted = all.length - raws.length;
  const budget = parsed.max_price_inr;

  if (all.length === 0) return null;

  const maxPrice = Math.max(budget ?? 0, ...raws.map((raw) => raw.priceInr), 1);
  const xMin = 0;
  const xStep = niceStep(maxPrice * 1.1 - xMin, 5);
  const xMax = Math.ceil((maxPrice * 1.08) / xStep) * xStep;
  const ratings = raws.map((raw) => raw.rating);
  const lowRating = ratings.length > 0 ? Math.min(...ratings) : 3;
  const highRating = ratings.length > 0 ? Math.max(...ratings) : 5;
  let yMin = Math.max(0, Math.floor(lowRating * 2) / 2 - 0.5);
  let yMax = Math.min(5, Math.ceil(highRating * 2) / 2 + 0.5);
  if (yMax - yMin < 1) {
    yMin = Math.max(0, yMax - 1);
    yMax = Math.min(5, yMin + 1);
  }
  const yStep = yMax - yMin > 2.5 ? 1 : 0.5;

  const etas = raws.flatMap((raw) => (raw.eta === null ? [] : [raw.eta]));
  const minEta = etas.length > 0 ? Math.min(...etas) : 0;
  const maxEta = etas.length > 0 ? Math.max(...etas) : 0;

  const plotW = WIDTH - MARGIN.left - MARGIN.right;
  const plotH = HEIGHT - MARGIN.top - MARGIN.bottom;
  const scaleX = (value: number) => MARGIN.left + ((value - xMin) / (xMax - xMin)) * plotW;
  const scaleY = (value: number) => MARGIN.top + (1 - (value - yMin) / (yMax - yMin)) * plotH;

  const order: Kind[] = ["excluded", "ranked", "pick"];
  const points: Point[] = order.flatMap((kind) =>
    raws
      .filter((raw) => raw.kind === kind)
      .map((raw) => ({
        ...raw,
        x: scaleX(raw.priceInr),
        y: scaleY(raw.rating),
        r: radiusFor(raw.eta, minEta, maxEta),
      })),
  );

  const xTicks = ticksBetween(xMin, xMax, xStep);
  const yTicks = ticksBetween(yMin, yMax, yStep);
  const activeId = pinned ?? hover;
  const active = points.find((point) => point.option.option_id === activeId) ?? null;
  const pickPoint = points.find((point) => point.kind === "pick") ?? null;

  const summary = pickPoint
    ? `Price against rating for ${raws.length} options; the pick is ${pickPoint.option.item} at ${rupeesInr(pickPoint.priceInr)} rated ${pickPoint.rating.toFixed(1)}`
    : `Price against rating for ${raws.length} options; there is no pick`;

  function toggle(id: string) {
    setPinned((current) => (current === id ? null : id));
  }

  function onKey(event: KeyboardEvent<SVGGElement>, id: string) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      toggle(id);
    } else if (event.key === "Escape") {
      setPinned(null);
      setHover(null);
    }
  }

  const tipPercentX = active ? (active.x / WIDTH) * 100 : 0;
  const tipPercentY = active ? (active.y / HEIGHT) * 100 : 0;
  const tipBelow = tipPercentY < 50;

  return (
    <section aria-labelledby="chart-heading">
      <h2 id="chart-heading" className="section-title">
        Price against rating
      </h2>
      <div className="card chart-card">
        {raws.length > 0 ? (
          <div className="chart-wrap" onClick={() => setPinned(null)}>
            <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label={summary} className="chart">
              {yTicks.map((tick) => (
                <g key={`y${tick}`}>
                  <line x1={MARGIN.left} x2={WIDTH - MARGIN.right} y1={scaleY(tick)} y2={scaleY(tick)} className="chart-grid" />
                  <text x={MARGIN.left - 6} y={scaleY(tick) + 4} textAnchor="end" className="chart-tick">
                    {tick.toFixed(1)}
                  </text>
                </g>
              ))}
              {xTicks.map((tick) => (
                <g key={`x${tick}`}>
                  <line x1={scaleX(tick)} x2={scaleX(tick)} y1={MARGIN.top} y2={HEIGHT - MARGIN.bottom} className="chart-grid" />
                  <text x={scaleX(tick)} y={HEIGHT - MARGIN.bottom + 16} textAnchor="middle" className="chart-tick">
                    {tick}
                  </text>
                </g>
              ))}
              <line
                x1={MARGIN.left}
                x2={WIDTH - MARGIN.right}
                y1={HEIGHT - MARGIN.bottom}
                y2={HEIGHT - MARGIN.bottom}
                className="chart-axis"
              />
              <line x1={MARGIN.left} x2={MARGIN.left} y1={MARGIN.top} y2={HEIGHT - MARGIN.bottom} className="chart-axis" />
              <text x={MARGIN.left + plotW / 2} y={HEIGHT - 6} textAnchor="middle" className="chart-label">
                Effective price (₹)
              </text>
              <text
                x={12}
                y={MARGIN.top + plotH / 2}
                textAnchor="middle"
                transform={`rotate(-90 12 ${MARGIN.top + plotH / 2})`}
                className="chart-label"
              >
                Rating (out of 5)
              </text>
              {budget !== null ? (
                <g>
                  <line
                    x1={scaleX(budget)}
                    x2={scaleX(budget)}
                    y1={MARGIN.top - 4}
                    y2={HEIGHT - MARGIN.bottom}
                    className="chart-budget"
                  />
                  <text
                    x={scaleX(budget)}
                    y={MARGIN.top - 8}
                    textAnchor={scaleX(budget) > WIDTH * 0.7 ? "end" : "start"}
                    className="chart-label"
                  >
                    {` Budget ${rupeesInr(budget)} `}
                  </text>
                </g>
              ) : null}
              {points.map((point) => {
                const id = point.option.option_id;
                const isActive = id === activeId;
                return (
                  <g
                    key={id}
                    tabIndex={0}
                    role="button"
                    aria-label={describe(point.option).join(". ")}
                    aria-pressed={pinned === id}
                    className={`dot dot-${point.kind}${isActive ? " dot-active" : ""}`}
                    onPointerEnter={() => setHover(id)}
                    onPointerLeave={() => setHover(null)}
                    onFocus={() => setHover(id)}
                    onBlur={() => setHover(null)}
                    onKeyDown={(event) => onKey(event, id)}
                    onClick={(event) => {
                      event.stopPropagation();
                      toggle(id);
                    }}
                  >
                    <circle cx={point.x} cy={point.y} r={point.r + 10} className="dot-hit" />
                    <circle cx={point.x} cy={point.y} r={point.r} className="dot-mark" />
                    {point.kind === "pick" ? (
                      <text
                        x={point.x + (point.x > WIDTH * 0.6 ? -point.r - 6 : point.r + 6)}
                        y={point.y - point.r - 4}
                        textAnchor={point.x > WIDTH * 0.6 ? "end" : "start"}
                        className="dot-label"
                      >
                        {`Pick: ${point.option.item}`}
                      </text>
                    ) : null}
                  </g>
                );
              })}
            </svg>
            {active ? (
              <div
                className="chart-tip"
                role="status"
                style={{
                  left: `${tipPercentX}%`,
                  top: `${tipPercentY}%`,
                  transform: `translate(-${tipPercentX}%, ${tipBelow ? "18px" : "calc(-100% - 18px)"})`,
                }}
              >
                {describe(active.option).map((line, index) => (
                  <p key={index} className={index === 0 ? "tip-title" : undefined}>
                    {line}
                  </p>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}
        <p className="chart-legend muted">
          <span className="legend-dot legend-pick" /> pick <span className="legend-dot legend-ranked" /> ranked{" "}
          <span className="legend-dot legend-excluded" /> filtered out · larger dot means faster delivery
        </p>
        {notPlotted > 0 ? <p className="muted">{notPlotted} not plotted (price or rating not listed)</p> : null}
      </div>
    </section>
  );
}
