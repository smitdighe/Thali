import type { ProviderReport, ProviderStatus } from "../types";
import { ms } from "../format";

interface Props {
  providers: ProviderReport[];
}

function statusClass(status: ProviderStatus): string {
  if (status === "ok") return "status-ok";
  if (status === "circuit_open") return "status-warn";
  return "status-bad";
}

export default function SourcesStrip({ providers }: Props) {
  return (
    <section aria-labelledby="sources-heading">
      <h2 id="sources-heading" className="section-title">
        Sources
      </h2>
      <ul className="pills">
        {providers.map((report) => (
          <li key={report.name} className={`pill ${statusClass(report.status)}`} title={report.message ?? undefined}>
            <strong>{report.label}</strong>
            <span className="pill-status">{report.status}</span>
            <span>{ms(report.latency_ms)}</span>
            <span>
              {report.records_used}/{report.records_received} records
            </span>
            {report.attempts > 1 ? <span>{report.attempts} tries</span> : null}
          </li>
        ))}
      </ul>
    </section>
  );
}
