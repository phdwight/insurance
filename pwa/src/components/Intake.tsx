import { useEffect, useState } from "react";
import { fetchProductLines, type ProductLine } from "../api";
import { SendIcon } from "./icons";

const ArrowIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <path
      d="M5 12h13M13 6l6 6-6 6"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);

const LockIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <rect x="4" y="10" width="16" height="10" rx="2" stroke="currentColor" strokeWidth="2" />
    <path d="M8 10V7a4 4 0 0 1 8 0v3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
  </svg>
);

export default function Intake(props: {
  onSubmit: (text: string, mode: "freeform" | "guided") => void;
}) {
  const [text, setText] = useState("");
  const [lines, setLines] = useState<ProductLine[]>([]);
  const [catalogError, setCatalogError] = useState(false);

  useEffect(() => {
    fetchProductLines()
      .then(setLines)
      .catch(() => setCatalogError(true));
  }, []);

  const available = lines.filter((line) => line.policy_count > 0);

  return (
    <section className="intake">
      <div className="intake-hero">
        <p className="eyebrow">AI Insurance Concierge</p>
        <h1>What would you like to protect?</h1>
        <p className="sub">
          Tell me in your own words — or I&rsquo;ll walk you through it, one question at a time.
        </p>

        <form
          className="hero-input"
          onSubmit={(event) => {
            event.preventDefault();
            if (text.trim()) props.onSubmit(text.trim(), "freeform");
          }}
        >
          <input
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder="e.g. life cover for my young family"
            aria-label="Describe what you want to protect"
          />
          <button type="submit" className="hero-send" disabled={!text.trim()} aria-label="Start">
            <SendIcon size={19} />
          </button>
        </form>

        {available.length > 0 && (
          <div className="chips">
            {available.map((line) => (
              <button
                key={line.code}
                className="chip"
                onClick={() => props.onSubmit(`I want ${line.code} insurance`, "guided")}
              >
                <span className="chip-dot" aria-hidden="true" />
                {line.name.replace(" Insurance", "")}
                <span className="chip-count">{line.policy_count}</span>
              </button>
            ))}
          </div>
        )}
        {catalogError && <p className="hint">Couldn&rsquo;t load categories — free text still works.</p>}

        <div className="divider">
          <span>or</span>
        </div>

        <button
          className="guided-card"
          onClick={() => props.onSubmit("I'm not sure where to start — guide me", "guided")}
        >
          <span className="guided-text">
            <strong>Not sure where to start?</strong>
            <span>I&rsquo;ll guide you, one question at a time</span>
          </span>
          <ArrowIcon />
        </button>

        <p className="footer-note">
          <LockIcon />
          Your details are encrypted and used only to match you with licensed insurers — never
          sold. Every plan is explained in plain English.
        </p>
      </div>
    </section>
  );
}

