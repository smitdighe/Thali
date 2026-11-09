import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, getHealth, recommend } from "./api";
import type { HealthResponse, RecommendResponse } from "./types";
import Header from "./components/Header";
import QueryForm from "./components/QueryForm";
import SourcesStrip from "./components/SourcesStrip";
import UnderstoodPanel from "./components/UnderstoodPanel";
import RecommendationCard from "./components/RecommendationCard";
import OptionsTable from "./components/OptionsTable";
import FilteredOut from "./components/FilteredOut";
import Footer from "./components/Footer";
import DemoControls from "./components/DemoControls";

type Phase = "idle" | "loading" | "done" | "error";

interface FailureInfo {
  message: string;
  requestId: string | null;
}

function describeFailure(error: unknown): FailureInfo {
  if (error instanceof ApiError) return { message: error.message, requestId: error.requestId };
  if (error instanceof Error) return { message: error.message, requestId: null };
  return { message: "Something went wrong.", requestId: null };
}

function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

export default function App() {
  const [phase, setPhase] = useState<Phase>("idle");
  const [response, setResponse] = useState<RecommendResponse | null>(null);
  const [error, setError] = useState<FailureInfo | null>(null);
  const [lastQuery, setLastQuery] = useState("");
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const controller = useRef<AbortController | null>(null);

  useEffect(() => {
    let active = true;
    getHealth()
      .then((result) => {
        if (active) setHealth(result);
      })
      .catch(() => {
        if (active) setHealth(null);
      });
    return () => {
      active = false;
      controller.current?.abort();
    };
  }, []);

  const submit = useCallback((query: string) => {
    controller.current?.abort();
    const next = new AbortController();
    controller.current = next;
    setLastQuery(query);
    setPhase("loading");
    setError(null);
    recommend(query, next.signal)
      .then((result) => {
        if (controller.current !== next) return;
        setResponse(result);
        setPhase("done");
      })
      .catch((caught: unknown) => {
        if (isAbort(caught) || controller.current !== next) return;
        setError(describeFailure(caught));
        setPhase("error");
      });
  }, []);

  const loading = phase === "loading";
  const showResponse = response !== null && (phase === "done" || phase === "loading");

  return (
    <div className="page">
      <Header health={health} />
      <QueryForm loading={loading} onSubmit={submit} />
      <div className="results" aria-live="polite">
        {loading ? <p className="loading-line">Reading your request · asking 3 sources…</p> : null}
        {phase === "error" && error ? (
          <div className="error-box" role="alert">
            <p>{error.message}</p>
            {error.requestId ? <p className="muted">Request {error.requestId}</p> : null}
            <button type="button" className="secondary" onClick={() => submit(lastQuery)}>
              Try again
            </button>
          </div>
        ) : null}
        {showResponse && response ? (
          <div className={loading ? "stale" : undefined}>
            <ResultBody response={response} />
          </div>
        ) : null}
      </div>
      <DemoControls />
    </div>
  );
}

function ResultBody({ response }: { response: RecommendResponse }) {
  const nothingFits = response.recommendation === null && response.clarification === null;
  return (
    <>
      {response.warnings.length > 0 ? (
        <div className="warnings">
          {response.warnings.map((warning, index) => (
            <p key={index}>{warning}</p>
          ))}
        </div>
      ) : null}
      <SourcesStrip providers={response.providers} />
      <UnderstoodPanel query={response.query} parsed={response.parsed} />
      {response.clarification ? (
        <section className="card clarification">
          <p className="card-label">Need one more detail</p>
          <p>{response.clarification}</p>
        </section>
      ) : null}
      {response.recommendation ? <RecommendationCard recommendation={response.recommendation} /> : null}
      {nothingFits ? (
        <section className="card nothing-fits">
          <p className="card-label">No match</p>
          <p>Nothing fits all of your requirements.</p>
          {response.closest.length > 0 ? (
            <>
              <h3 className="sub-title">Closest options</h3>
              <ul>
                {response.closest.map((option) => (
                  <li key={option.option_id}>
                    {option.item} · {option.restaurant}
                    {option.area ? ` (${option.area})` : ""}
                    {option.best.violations.length > 0 ? ` — ${option.best.violations.join("; ")}` : ""}
                  </li>
                ))}
              </ul>
            </>
          ) : null}
        </section>
      ) : null}
      {response.ranked.length > 0 ? <OptionsTable options={response.ranked} /> : null}
      {response.excluded.length > 0 ? <FilteredOut options={response.excluded} /> : null}
      <Footer response={response} />
    </>
  );
}
