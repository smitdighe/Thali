import { useState } from "react";
import type { KeyboardEvent, ReactNode } from "react";

export interface TabDef {
  id: string;
  label: string;
  content: ReactNode;
}

interface Props {
  label: string;
  tabs: TabDef[];
}

export default function Tabs({ label, tabs }: Props) {
  const [selected, setSelected] = useState(tabs[0]?.id ?? "");
  const active = tabs.find((tab) => tab.id === selected) ?? tabs[0];

  function activate(index: number) {
    const target = tabs[(index + tabs.length) % tabs.length];
    if (!target) return;
    setSelected(target.id);
    document.getElementById(`tab-${target.id}`)?.focus();
  }

  function onKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    if (event.key === "ArrowRight") activate(index + 1);
    else if (event.key === "ArrowLeft") activate(index - 1);
    else if (event.key === "Home") activate(0);
    else if (event.key === "End") activate(tabs.length - 1);
    else return;
    event.preventDefault();
  }

  if (!active) return null;

  return (
    <div className="tabs">
      <div role="tablist" aria-label={label} className="tablist">
        {tabs.map((tab, index) => {
          const isActive = tab.id === active.id;
          return (
            <button
              key={tab.id}
              id={`tab-${tab.id}`}
              type="button"
              role="tab"
              className="tab"
              aria-selected={isActive}
              aria-controls={`panel-${tab.id}`}
              tabIndex={isActive ? 0 : -1}
              onClick={() => setSelected(tab.id)}
              onKeyDown={(event) => onKeyDown(event, index)}
            >
              {tab.label}
            </button>
          );
        })}
      </div>
      <div
        id={`panel-${active.id}`}
        role="tabpanel"
        aria-labelledby={`tab-${active.id}`}
        tabIndex={0}
        className="tabpanel"
      >
        {active.content}
      </div>
    </div>
  );
}
