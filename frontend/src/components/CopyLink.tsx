import { useEffect, useRef, useState } from "react";

type CopyState = "idle" | "copied" | "failed";

export default function CopyLink() {
  const [state, setState] = useState<CopyState>("idle");
  const timer = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (timer.current !== null) window.clearTimeout(timer.current);
    };
  }, []);

  function finish(next: CopyState) {
    setState(next);
    if (timer.current !== null) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setState("idle"), 1800);
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(window.location.href);
      finish("copied");
    } catch {
      finish("failed");
    }
  }

  const label = state === "copied" ? "Copied" : state === "failed" ? "Copy failed" : "Copy link";
  return (
    <button type="button" className="secondary" onClick={copy}>
      <span aria-live="polite">{label}</span>
    </button>
  );
}
