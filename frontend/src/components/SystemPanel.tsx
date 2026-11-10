import { useEffect, useState } from "react";
import { getMetrics } from "../api";
import { ms } from "../format";
import type { BreakerState, MetricsResponse } from "../types";

const POLL_MS = 5000;
const WIDTH = 240;
const HEIGHT = 48;

const BREAKER_TEXT: Record<BreakerState, string> = {
  closed: "closed",
  open: "open",
  half_open: "half open",
};

function points(values: number[]): string {
  const max = Math.max(...values);
  const scale = max > 0 ? max : 1;
  const step = WIDTH / (values.length - 1);
  return values
    .map((value, index) => `${(index * step).toFixed(1)},${(HEIGHT - (value / scale) * HEIGHT).toFixed(1)}`)
    .join(" ");
}

function Sparkline({ values }: { values: number[] }) {
  if (values.length < 2) return <p className="muted">Run a few requests to see the trend.</p>;
  const label = `Last ${values.length} request times, ${ms(Math.min(...values))} to ${ms(Math.max(...values))}`;
  return (
    <div className="sparkline-row">
      <svg
        className="sparkline"
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        width="100%"
        height={HEIGHT}
        preserveAspectRatio="none"
        role="img"
        aria-label={label}
      >
        <polyline points={points(values)} vectorEffect="non-scaling-stroke" />
      </svg>
      <span className="muted">Last {values.length} requests</span>
    </div>
  );
}

export default function SystemPanel() {
  const [metrics, setMetrics] = useState<MetricsResponse | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let controller: AbortController | null = null;

    async function load() {
      if (document.hidden) return;
      controller?.abort();
      const current = new AbortController();
      controller = current;
      try {
        const data = await getMetrics(current.signal);
        if (current.signal.aborted) return;
        setMetrics(data);
        setFailed(false);
      } catch (error) {
        if (current.signal.aborted) return;
        if (error instanceof DOMException && error.name === "AbortError") return;
        setFailed(true);
      }
    }

    void load();
    const timer = window.setInterval(() => {
      void load();
    }, POLL_MS);
    return () => {
      window.clearInterval(timer);
      controller?.abort();
    };
  }, []);

  return (
    <section>
      <h2 className="section-title">System</h2>
      {failed ? <p className="error-text">Could not load metrics.</p> : null}
      {metrics === null ? (
        failed ? null : <p className="muted">Loading metrics…</p>
      ) : (
        <>
          <div className="system-stats">
            <span>
              Requests {metrics.requests} · p50 {ms(metrics.p50_ms)} · p95 {ms(metrics.p95_ms)}
            </span>
            <span>
              Parser: rules {metrics.parser.rules} · LLM {metrics.parser.llm} · fallbacks {metrics.parser.fallbacks}
            </span>
          </div>
          <Sparkline values={metrics.recent_total_ms} />
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Source</th>
                  <th className="num">Calls</th>
                  <th className="num">OK rate</th>
                  <th className="num">p50</th>
                  <th className="num">p95</th>
                  <th className="num">Timeouts</th>
                  <th className="num">Errors</th>
                  <th>Breaker</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(metrics.providers).map(([name, row]) => {
                  const idle = row.calls === 0;
                  return (
                    <tr key={name}>
                      <td>{name}</td>
                      <td className="num">{row.calls}</td>
                      <td className="num">{idle ? "–" : `${Math.round(row.ok_rate * 100)}%`}</td>
                      <td className="num">{idle ? "–" : ms(row.p50_ms)}</td>
                      <td className="num">{idle ? "–" : ms(row.p95_ms)}</td>
                      <td className="num">{row.timeouts}</td>
                      <td className="num">{row.errors}</td>
                      <td className={`breaker-${row.breaker}`}>{BREAKER_TEXT[row.breaker]}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}
