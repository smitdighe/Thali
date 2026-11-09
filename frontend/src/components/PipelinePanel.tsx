import { useEffect, useState } from "react";
import type { Attempt, ProviderReport, ProviderStatus, RecommendResponse } from "../types";
import { ms } from "../format";

interface Props {
  loading: boolean;
  startedAt: number | null;
  parsedSeen: boolean;
  liveProviders: ProviderReport[];
  response: RecommendResponse | null;
}

interface SourceRow {
  name: string;
  label: string;
}

const SOURCES: SourceRow[] = [
  { name: "bitebox", label: "Bitebox" },
  { name: "tiffinly", label: "Tiffinly" },
  { name: "khaana", label: "Khaana" },
];

const BASE_AXIS_MS = 2000;
const TICK_COUNT = 4;

function useElapsed(startedAt: number | null, active: boolean): number {
  const [now, setNow] = useState(() => performance.now());
  useEffect(() => {
    if (!active) return;
    setNow(performance.now());
    const timer = window.setInterval(() => setNow(performance.now()), 100);
    return () => window.clearInterval(timer);
  }, [active]);
  if (startedAt === null) return 0;
  return Math.max(0, now - startedAt);
}

function axisMax(reports: ProviderReport[]): number {
  let max = BASE_AXIS_MS;
  for (const report of reports) {
    for (const attempt of report.attempt_log) {
      max = Math.max(max, attempt.start_ms + attempt.duration_ms);
    }
  }
  return Math.ceil(max / 500) * 500;
}

function statusText(status: ProviderStatus): string {
  return status === "circuit_open" ? "circuit open" : status;
}

function statusClass(status: ProviderStatus): string {
  if (status === "ok") return "status-ok";
  if (status === "circuit_open") return "status-warn";
  return "status-bad";
}

function segmentClass(attempt: Attempt): string {
  if (attempt.outcome === "ok") return "seg seg-ok";
  if (attempt.outcome === "timeout") return "seg seg-timeout";
  if (attempt.outcome === "skipped") return "seg seg-skipped";
  return "seg seg-fail";
}

function segmentTitle(attempt: Attempt): string {
  if (attempt.outcome === "skipped") return "skipped (circuit open)";
  const parts = [attempt.outcome.replace("_", " "), ms(attempt.duration_ms)];
  if (attempt.http_status !== null) parts.push(`HTTP ${attempt.http_status}`);
  return parts.join(" · ");
}

function Segment({ attempt, axis }: { attempt: Attempt; axis: number }) {
  const left = (attempt.start_ms / axis) * 100;
  const width = attempt.outcome === "skipped" ? 0 : (attempt.duration_ms / axis) * 100;
  return (
    <span
      className={segmentClass(attempt)}
      style={{ left: `${left}%`, width: width > 0 ? `${width}%` : undefined }}
      title={segmentTitle(attempt)}
    />
  );
}

function Ticks({ axis }: { axis: number }) {
  const ticks = Array.from({ length: TICK_COUNT + 1 }, (_, index) => (axis / TICK_COUNT) * index);
  return (
    <>
      {ticks.map((tick) => (
        <span key={tick} className="tick-line" style={{ left: `${(tick / axis) * 100}%` }} />
      ))}
    </>
  );
}

function ProviderRow({
  source,
  report,
  axis,
  elapsed,
  waiting,
}: {
  source: SourceRow;
  report: ProviderReport | null;
  axis: number;
  elapsed: number;
  waiting: boolean;
}) {
  const skippedOnly = report !== null && report.attempt_log.length > 0 && report.attempt_log.every(isSkipped);
  return (
    <li className="pipe-row">
      <div className="pipe-label">
        <strong>{source.label}</strong>
        {report ? (
          <span className={`pipe-meta ${statusClass(report.status)}`}>
            <span className="pill-status">{statusText(report.status)}</span> · {ms(report.latency_ms)}
          </span>
        ) : (
          <span className="pipe-meta muted">{waiting ? `waiting ${ms(elapsed)}` : "not run"}</span>
        )}
      </div>
      <div className="pipe-track">
        <Ticks axis={axis} />
        {report
          ? report.attempt_log.map((attempt, index) => <Segment key={index} attempt={attempt} axis={axis} />)
          : null}
        {skippedOnly ? <span className="pipe-note">skipped (circuit open)</span> : null}
      </div>
    </li>
  );
}

function isSkipped(attempt: Attempt): boolean {
  return attempt.outcome === "skipped";
}

function StepRow({ label, value, pending }: { label: string; value: string; pending: boolean }) {
  return (
    <li className="pipe-row">
      <div className="pipe-label">
        <strong>{label}</strong>
        <span className={pending ? "pipe-meta muted" : "pipe-meta"}>{value}</span>
      </div>
    </li>
  );
}

export default function PipelinePanel({ loading, startedAt, parsedSeen, liveProviders, response }: Props) {
  const elapsed = useElapsed(startedAt, loading);
  const reports = response ? response.providers : liveProviders;
  const axis = axisMax(reports);
  const extra = reports.filter((report) => !SOURCES.some((source) => source.name === report.name));
  const rows: SourceRow[] = [...SOURCES, ...extra.map((report) => ({ name: report.name, label: report.label }))];
  const trace = response ? response.trace : null;

  let understand = "not run";
  if (trace) understand = ms(trace.parse_ms);
  else if (loading) understand = parsedSeen ? "done" : `waiting ${ms(elapsed)}`;

  let rank = "not run";
  if (trace) rank = `${ms(trace.rank_ms)} + ${ms(trace.what_if_ms)} what-if`;
  else if (loading) rank = `waiting ${ms(elapsed)}`;

  const ticks = Array.from({ length: TICK_COUNT + 1 }, (_, index) => (axis / TICK_COUNT) * index);

  return (
    <section className="card pipeline" aria-labelledby="pipeline-heading">
      <h2 id="pipeline-heading" className="section-title">
        How this answer was made
      </h2>
      <ol className="pipe-list">
        <StepRow label="Understand" value={understand} pending={trace === null} />
        <li className="pipe-axis" aria-hidden="true">
          <div className="pipe-label" />
          <div className="pipe-track pipe-axis-track">
            {ticks.map((tick) => (
              <span key={tick} className="tick-label" style={{ left: `${(tick / axis) * 100}%` }}>
                {tick}
              </span>
            ))}
          </div>
        </li>
        {rows.map((source) => (
          <ProviderRow
            key={source.name}
            source={source}
            report={reports.find((report) => report.name === source.name) ?? null}
            axis={axis}
            elapsed={elapsed}
            waiting={loading}
          />
        ))}
        <StepRow label="Rank & explain" value={rank} pending={trace === null} />
      </ol>
      <p className="pipe-legend muted">
        <span className="legend-chip seg-ok" /> ok <span className="legend-chip seg-fail" /> failed{" "}
        <span className="legend-chip seg-timeout" /> timeout <span className="legend-chip seg-skipped" /> skipped · time
        axis in ms
      </p>
    </section>
  );
}
