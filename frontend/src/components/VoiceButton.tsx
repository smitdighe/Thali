import { useEffect, useRef, useState } from "react";

interface Props {
  disabled: boolean;
  onInterim: (text: string) => void;
  onFinal: (text: string) => void;
  onError: (message: string | null) => void;
}

function constructorOf(): SpeechRecognitionConstructorLike | null {
  const source = window as Window & SpeechWindow;
  return source.SpeechRecognition ?? source.webkitSpeechRecognition ?? null;
}

function errorMessage(code: string): string | null {
  if (code === "not-allowed" || code === "service-not-allowed") {
    return "Microphone access was denied. Allow it in the browser settings to use voice input.";
  }
  if (code === "no-speech") return "No speech heard. Try again.";
  if (code === "aborted") return null;
  return `Voice input failed (${code}).`;
}

function transcriptOf(event: SpeechResultEventLike): { text: string; final: boolean } {
  let text = "";
  let final = true;
  for (let index = 0; index < event.results.length; index += 1) {
    const result = event.results[index];
    if (!result) continue;
    text += result[0]?.transcript ?? "";
    if (!result.isFinal) final = false;
  }
  return { text: text.trim(), final };
}

export default function VoiceButton({ disabled, onInterim, onFinal, onError }: Props) {
  const [listening, setListening] = useState(false);
  const recognition = useRef<SpeechRecognitionLike | null>(null);
  const Ctor = constructorOf();

  useEffect(() => {
    return () => recognition.current?.abort();
  }, []);

  if (Ctor === null) return null;

  function toggle() {
    if (!Ctor) return;
    if (recognition.current) {
      recognition.current.stop();
      return;
    }
    const next = new Ctor();
    next.lang = "en-IN";
    next.interimResults = true;
    next.continuous = false;
    next.onresult = (event) => {
      const { text, final } = transcriptOf(event);
      if (text.length === 0) return;
      if (final) onFinal(text);
      else onInterim(text);
    };
    next.onerror = (event) => onError(errorMessage(event.error));
    next.onend = () => {
      recognition.current = null;
      setListening(false);
    };
    onError(null);
    recognition.current = next;
    setListening(true);
    try {
      next.start();
    } catch {
      recognition.current = null;
      setListening(false);
      onError("Voice input could not start.");
    }
  }

  return (
    <button
      type="button"
      className={listening ? "mic secondary listening" : "mic secondary"}
      aria-label={listening ? "Stop voice input" : "Start voice input"}
      aria-pressed={listening}
      disabled={disabled}
      onClick={toggle}
    >
      <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false">
        <rect x="9" y="3" width="6" height="12" rx="3" fill="none" stroke="currentColor" strokeWidth="2" />
        <path d="M5 11a7 7 0 0 0 14 0M12 18v3" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      </svg>
    </button>
  );
}
