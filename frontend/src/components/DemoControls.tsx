import { useEffect, useState } from "react";
import { getFaults, resetFaults, setFaults } from "../api";
import type { FaultMode, FaultState, ProviderName } from "../types";

const PROVIDERS: ProviderName[] = ["bitebox", "tiffinly", "khaana"];
const MODES: FaultMode[] = ["ok", "slow", "timeout", "error", "malformed", "partial"];

function isFaultMode(value: string): value is FaultMode {
  return MODES.some((mode) => mode === value);
}

function messageOf(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

export default function DemoControls() {
  const [faults, setFaultState] = useState<FaultState | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    getFaults()
      .then((state) => {
        if (active) setFaultState(state);
      })
      .catch(() => {
        if (active) setFaultState(null);
      });
    return () => {
      active = false;
    };
  }, []);

  if (faults === null) return null;

  function change(name: ProviderName, value: string) {
    if (!isFaultMode(value)) return;
    setProblem(null);
    setFaults({ [name]: value })
      .then(setFaultState)
      .catch((error: unknown) => setProblem(messageOf(error, "Could not update the mock providers.")));
  }

  function reset() {
    setProblem(null);
    resetFaults()
      .then(setFaultState)
      .catch((error: unknown) => setProblem(messageOf(error, "Could not reset the mock providers.")));
  }

  return (
    <details className="card demo-controls">
      <summary>Simulate provider problems</summary>
      <div className="demo-grid">
        {PROVIDERS.map((name) => (
          <label key={name} className="demo-field">
            <span>{name}</span>
            <select value={faults[name]} onChange={(event) => change(name, event.target.value)}>
              {MODES.map((mode) => (
                <option key={mode} value={mode}>
                  {mode}
                </option>
              ))}
            </select>
          </label>
        ))}
        <button type="button" className="secondary" onClick={reset}>
          Reset
        </button>
      </div>
      <p className="muted">These change the mock providers, not the engine. Run the request again to see the effect.</p>
      {problem ? <p className="error-text">{problem}</p> : null}
    </details>
  );
}
