import type { RecommendResponse, RefineAction } from "../types";
import PipelinePanel from "./PipelinePanel";
import SourcesStrip from "./SourcesStrip";
import UnderstoodPanel from "./UnderstoodPanel";
import RecommendationCard from "./RecommendationCard";
import TradeoffChart from "./TradeoffChart";
import WhatIfList from "./WhatIfList";
import OptionsTable from "./OptionsTable";
import FilteredOut from "./FilteredOut";
import RefineRow from "./RefineRow";
import Tabs from "./Tabs";
import type { TabDef } from "./Tabs";

export interface RefineControls {
  busy: boolean;
  error: string | null;
  onAction: (action: RefineAction, label: string) => void;
  onText: (text: string) => void;
  onDrop: (field: string) => void;
}

interface Props {
  response: RecommendResponse;
  controls: RefineControls;
  loading: boolean;
  startedAt: number | null;
}

export default function ResultBody({ response, controls, loading, startedAt }: Props) {
  const nothingFits = response.recommendation === null && response.clarification === null;

  const compare = (
    <>
      <TradeoffChart
        recommendation={response.recommendation}
        ranked={response.ranked}
        excluded={response.excluded}
        parsed={response.parsed}
      />
      {response.ranked.length > 0 ? <OptionsTable options={response.ranked} /> : null}
      {response.excluded.length > 0 ? <FilteredOut options={response.excluded} /> : null}
      {response.ranked.length === 0 && response.excluded.length === 0 ? (
        <p className="muted">No options to compare.</p>
      ) : null}
    </>
  );

  const decided = (
    <>
      {loading ? null : (
        <PipelinePanel loading={false} startedAt={startedAt} parsedSeen liveProviders={[]} response={response} />
      )}
      <SourcesStrip providers={response.providers} />
      <WhatIfList items={response.what_if} />
    </>
  );

  const tabs: TabDef[] = [
    { id: "compare", label: "Compare", content: compare },
    { id: "decided", label: "How it decided", content: decided },
  ];

  return (
    <>
      {response.warnings.length > 0 ? (
        <div className="warnings">
          {response.warnings.map((warning, index) => (
            <p key={index}>{warning}</p>
          ))}
        </div>
      ) : null}
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
      {response.clarification === null ? <Tabs label="Details" tabs={tabs} /> : null}
    </>
  );
}
