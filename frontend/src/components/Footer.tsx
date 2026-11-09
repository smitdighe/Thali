import type { RecommendResponse } from "../types";
import { ms } from "../format";

interface Props {
  response: RecommendResponse | null;
}

export default function Footer({ response }: Props) {
  if (response === null) {
    return (
      <footer className="site-footer muted">
        <p>
          <a href="/docs">API docs</a>
        </p>
      </footer>
    );
  }
  const { data_quality: quality, trace } = response;
  return (
    <footer className="site-footer muted">
      <p>
        Received {quality.records_received} records · dropped {quality.records_dropped} · merged{" "}
        {quality.duplicates_removed} duplicates across sources · {quality.listings_with_missing_fields} listings
        missing fields
      </p>
      <p>
        parse {ms(trace.parse_ms)} · fetch {ms(trace.fetch_ms)} · rank {ms(trace.rank_ms)} · what-if{" "}
        {ms(trace.what_if_ms)} · total {ms(trace.total_ms)} · request {response.request_id}
      </p>
      <p>
        <a href="/docs">API docs</a>
      </p>
      <details>
        <summary>Raw response</summary>
        <pre className="raw">{JSON.stringify(response, null, 2)}</pre>
      </details>
    </footer>
  );
}
