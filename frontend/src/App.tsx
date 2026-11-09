import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, getHealth, recommendStream, refine } from "./api";
import type { HealthResponse, ProviderReport, RecommendResponse, RefineAction, RefineRequest } from "./types";
import { fieldLabel } from "./fields";
import Header from "./components/Header";
import QueryForm from "./components/QueryForm";
import Breadcrumbs from "./components/Breadcrumbs";
import RefineRow from "./components/RefineRow";
import PipelinePanel from "./components/PipelinePanel";
import SourcesStrip from "./components/SourcesStrip";
import UnderstoodPanel from "./components/UnderstoodPanel";
import RecommendationCard from "./components/RecommendationCard";
import TradeoffChart from "./components/TradeoffChart";
import WhatIfList from "./components/WhatIfList";
import OptionsTable from "./components/OptionsTable";
import FilteredOut from "./components/FilteredOut";
import Footer from "./components/Footer";
import DemoControls from "./components/DemoControls";

type Phase = "idle" | "loading" | "done" | "error";

interface LiveState {
  startedAt: number;
  parsedSeen: boolean;
  providers: ProviderReport[];
}

interface HistoryEntry {
  label: string;
  response: RecommendResponse;
}

interface RefineControls {
  busy: boolean;
  error: string | null;
  onAction: (action: RefineAction, label: string) => void;
  onText: (text: string) => void;
  onDrop: (field: string) => void;
}

interface FailureInfo {
  message: string;
  requestId: string | null;
}

function describeFailure(error: unknown): FailureInfo {
  if (error instanceof ApiError) return { message: error.message, requestId: error.requestId };
  if (error instanceof Error) return { message: error.message, requestId: null };
  return { message: "Something went wrong.", requestId: null };
}

function refineMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 404) return "This request expired. Run it again.";
  if (error instanceof ApiError && error.status === 409) return "There is no pick to refine.";
  return describeFailure(error).message;
}

function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

export default function App() {
  const [phase, setPhase] = useState<Phase>("idle");
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [viewIndex, setViewIndex] = useState(0);
  const [refining, setRefining] = useState(false);
  const [refineError, setRefineError] = useState<string | null>(null);
  const [error, setError] = useState<FailureInfo | null>(null);
  const [lastQuery, setLastQuery] = useState("");
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [live, setLive] = useState<LiveState | null>(null);
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
    setRefining(false);
    setRefineError(null);
    setLive({ startedAt: performance.now(), parsedSeen: false, providers: [] });
    const current = () => controller.current === next;
    recommendStream(query, next.signal, {
      onParsed: () => {
        if (current()) setLive((state) => (state ? { ...state, parsedSeen: true } : state));
      },
      onProvider: (report) => {
        if (current()) setLive((state) => (state ? { ...state, providers: [...state.providers, report] } : state));
      },
    })
      .then((result) => {
        if (controller.current !== next) return;
        setHistory([{ label: "Your request", response: result }]);
        setViewIndex(0);
        setPhase("done");
      })
      .catch((caught: unknown) => {
        if (isAbort(caught) || controller.current !== next) return;
        setError(describeFailure(caught));
        setPhase("error");
      });
  }, []);

  const runRefine = useCallback(
    (body: Omit<RefineRequest, "request_id">, label: string) => {
      const base = history[viewIndex];
      if (!base) return;
      controller.current?.abort();
      const next = new AbortController();
      controller.current = next;
      setRefining(true);
      setRefineError(null);
      refine({ request_id: base.response.request_id, ...body }, next.signal)
        .then((result) => {
          if (controller.current !== next) return;
          setHistory((entries) => [...entries.slice(0, viewIndex + 1), { label, response: result }]);
          setViewIndex(viewIndex + 1);
          setRefining(false);
        })
        .catch((caught: unknown) => {
          if (isAbort(caught) || controller.current !== next) return;
          setRefineError(refineMessage(caught));
          setRefining(false);
        });
    },
    [history, viewIndex],
  );

  const controls: RefineControls = {
    busy: refining,
    error: refineError,
    onAction: (action, label) => runRefine({ action }, label),
    onText: (text) => runRefine({ text }, text),
    onDrop: (field) => runRefine({ drop: field }, `Removed ${fieldLabel(field)}`),
  };

  const response = history[viewIndex]?.response ?? null;
  const loading = phase === "loading";
  const showResponse = response !== null && (phase === "done" || phase === "loading");

  return (
    <div className="page">
      <Header health={health} />
      <QueryForm loading={loading} onSubmit={submit} />
      <div className="results" aria-live="polite">
        {loading ? <p className="loading-line">Reading your request · asking 3 sources…</p> : null}
        {live && (loading || (phase === "done" && response)) ? (
          <PipelinePanel
            loading={loading}
            startedAt={live.startedAt}
            parsedSeen={live.parsedSeen}
            liveProviders={live.providers}
            response={loading ? null : response}
          />
        ) : null}
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
          <div className={loading || refining ? "stale" : undefined}>
            <Breadcrumbs
              labels={history.map((entry) => entry.label)}
              current={viewIndex}
              onSelect={(index) => {
                setViewIndex(index);
                setRefineError(null);
              }}
            />
            <ResultBody response={response} controls={controls} />
          </div>
        ) : null}
      </div>
      <DemoControls />
    </div>
  );
}

function ResultBody({ response, controls }: { response: RecommendResponse; controls: RefineControls }) {
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
      <UnderstoodPanel query={response.query} parsed={response.parsed} busy={controls.busy} onDrop={controls.onDrop} />
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
      {response.request_id && response.clarification === null ? (
        <RefineRow
          hasPick={response.recommendation !== null}
          busy={controls.busy}
          error={controls.error}
          onAction={controls.onAction}
          onText={controls.onText}
        />
      ) : null}
      <WhatIfList items={response.what_if} />
      <TradeoffChart
        recommendation={response.recommendation}
        ranked={response.ranked}
        excluded={response.excluded}
        parsed={response.parsed}
      />
      {response.ranked.length > 0 ? <OptionsTable options={response.ranked} /> : null}
      {response.excluded.length > 0 ? <FilteredOut options={response.excluded} /> : null}
      <Footer response={response} />
    </>
  );
}
