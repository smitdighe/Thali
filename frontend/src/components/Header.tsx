import type { HealthResponse } from "../types";

interface Props {
  health: HealthResponse | null;
}

function parsingLabel(health: HealthResponse | null): string {
  if (health === null) return "Parsing mode unavailable";
  if (health.llm_enabled) return `LLM parsing on · ${health.llm_model ?? "model not listed"}`;
  return "Rule-based parsing (no LLM key)";
}

export default function Header({ health }: Props) {
  return (
    <header className="site-header">
      <div>
        <h1>Thali</h1>
        <p className="muted">Mini FLOUNA decision engine</p>
      </div>
      <p className="badge">{parsingLabel(health)}</p>
    </header>
  );
}
