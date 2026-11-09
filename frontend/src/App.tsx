import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, getHealth, recommendStream, refine } from "./api";
import type { HealthResponse, ProviderReport, RecommendResponse, RefineRequest } from "./types";
import { fieldLabel } from "./fields";
import Header from "./components/Header";
import QueryForm from "./components/QueryForm";
import ExampleChips from "./components/ExampleChips";
import CopyLink from "./components/CopyLink";
import Breadcrumbs from "./components/Breadcrumbs";
import PipelinePanel from "./components/PipelinePanel";
import ResultBody from "./components/ResultBody";
import type { RefineControls } from "./components/ResultBody";
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

function rememberQuery(text: string): void {
  try {
    const url = new URL(window.location.href);
    url.searchParams.set("q", text);
    window.history.replaceState(null, "", url);
  } catch {
    return;
  }
}

function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName);
}

export default function App() {
  const [phase, setPhase] = useState<Phase>("idle");
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [viewIndex, setViewIndex] = useState(0);
  const [refining, setRefining] = useState(false);
  const [refineError, setRefineError] = useState<string | null>(null);
  const [error, setError] = useState<FailureInfo | null>(null);
  const [lastQuery, setLastQuery] = useState("");
  const [query, setQuery] = useState("");
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [live, setLive] = useState<LiveState | null>(null);
  const controller = useRef<AbortController | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

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

  const submit = useCallback((text: string) => {
    controller.current?.abort();
    const next = new AbortController();
    controller.current = next;
    setQuery(text);
    setLastQuery(text);
    rememberQuery(text);
    setPhase("loading");
    setError(null);
    setRefining(false);
    setRefineError(null);
    setLive({ startedAt: performance.now(), parsedSeen: false, providers: [] });
    const current = () => controller.current === next;
    recommendStream(text, next.signal, {
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

  useEffect(() => {
    const initial = new URLSearchParams(window.location.search).get("q");
    if (initial && initial.trim().length > 0) submit(initial.trim());
  }, [submit]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key !== "/" || event.ctrlKey || event.metaKey || event.altKey) return;
      if (isTypingTarget(event.target)) return;
      event.preventDefault();
      inputRef.current?.focus();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
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
      <div className="query-bar">
        <QueryForm
          value={query}
          lastQuery={lastQuery}
          loading={loading}
          inputRef={inputRef}
          onChange={setQuery}
          onSubmit={submit}
        />
      </div>
      <ExampleChips collapsed={showResponse} onPick={submit} />
      <div className="results" aria-live="polite">
        {loading ? <p className="loading-line">Reading your request · asking 3 sources…</p> : null}
        {live && loading ? (
          <PipelinePanel
            loading
            startedAt={live.startedAt}
            parsedSeen={live.parsedSeen}
            liveProviders={live.providers}
            response={null}
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
            <div className="trail">
              <Breadcrumbs
                labels={history.map((entry) => entry.label)}
                current={viewIndex}
                onSelect={(index) => {
                  setViewIndex(index);
                  setRefineError(null);
                }}
              />
              <CopyLink />
            </div>
            <ResultBody response={response} controls={controls} loading={loading} startedAt={live?.startedAt ?? null} />
          </div>
        ) : null}
      </div>
      <DemoControls />
      <Footer response={showResponse ? response : null} />
    </div>
  );
}
