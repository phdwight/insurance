import { useState } from "react";
import { fetchComparison, type Comparison, type Recommendation, type Recommendations } from "../api";

function peso(value: string | number | null): string {
  if (value === null || value === undefined) return "—";
  return `₱${Number(value).toLocaleString()}`;
}

/** Normalize a value for display: treat JS null/undefined AND null-ish strings
 *  ("null", "undefined", "none", empty) that leak through from extraction as
 *  genuinely missing, so the raw word "null" never reaches the user. */
function clean(value: unknown): string | null {
  if (value === null || value === undefined) return null;
  const text = String(value).trim();
  if (!text || ["null", "undefined", "none", "n/a"].includes(text.toLowerCase())) return null;
  return text;
}

function renderValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "boolean") return value ? "yes" : "no";
  if (Array.isArray(value)) return value.length ? value.join("; ") : "—";
  if (typeof value === "object") {
    return Object.entries(value as Record<string, unknown>)
      .filter(([key, v]) => v !== null && v !== undefined && key !== "line")
      .map(([key, v]) => `${key.replaceAll("_", " ")}: ${renderValue(v)}`)
      .join(" · ") || "—";
  }
  return clean(value) ?? "—";
}

const COMPARE_ROWS = [
  "insurer_name",
  "premium_min",
  "premium_max",
  "premium_frequency",
  "eligibility",
  "coverage",
  "exclusions",
  "verified_at",
];

function PolicyCard(props: {
  policy: Recommendation;
  selected: boolean;
  onToggle: () => void;
}) {
  const { policy } = props;
  return (
    <article className={`policy-card ${props.selected ? "selected" : ""}`}>
      <header>
        <label className="compare-pick">
          <input type="checkbox" checked={props.selected} onChange={props.onToggle} />
          compare
        </label>
        <h3>{policy.name}</h3>
        <p className="insurer">{clean(policy.insurer_name) ?? "Insurer not specified"}</p>
      </header>
      <p className="premium">
        {peso(policy.premium_min)} – {peso(policy.premium_max)}
        {policy.premium_frequency && (
          <span className="freq">
            {" "}
            {policy.premium_frequency === "single" ? "one-time" : policy.premium_frequency}
          </span>
        )}
      </p>
      <ul className="reasons">
        {policy.match_reasons?.map((reason, index) => <li key={index}>{reason}</li>)}
      </ul>
      {policy.exclusions?.length > 0 && (
        <p className="exclusions">Key exclusions: {policy.exclusions.join("; ")}</p>
      )}
      <footer>
        {policy.verified_at && (
          <span className="verified">
            Data as of {new Date(policy.verified_at).toLocaleDateString()}
          </span>
        )}
        {policy.source_url && (
          <a href={policy.source_url} target="_blank" rel="noreferrer">
            Official document
          </a>
        )}
      </footer>
    </article>
  );
}

function ComparisonTable(props: { comparison: Comparison }) {
  const slugs = props.comparison.policies;
  const rows = props.comparison.comparison;
  return (
    <div className="compare-table-wrap">
      <table className="compare-table">
        <thead>
          <tr>
            <th>Attribute</th>
            {slugs.map((slug) => (
              <th key={slug}>{String(rows.name?.[slug] ?? slug)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {COMPARE_ROWS.filter((field) => rows[field]).map((field) => (
            <tr key={field}>
              <td className="attr">{field.replaceAll("_", " ")}</td>
              {slugs.map((slug) => (
                <td key={slug}>{renderValue(rows[field]?.[slug])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function Results(props: { recommendations: Recommendations }) {
  const [selected, setSelected] = useState<string[]>([]);
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [error, setError] = useState("");

  const lines = Object.entries(props.recommendations).filter(
    ([, policies]) => policies.length > 0,
  );
  if (lines.length === 0) return null;

  function toggle(slug: string) {
    setComparison(null);
    setSelected((current) =>
      current.includes(slug)
        ? current.filter((s) => s !== slug)
        : current.length < 4
          ? [...current, slug]
          : current,
    );
  }

  async function compare() {
    try {
      setError("");
      setComparison(await fetchComparison(selected));
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : "comparison failed");
    }
  }

  return (
    <div className="results">
      {lines.map(([line, policies]) => (
        <section key={line}>
          <h2>{line.charAt(0).toUpperCase() + line.slice(1)} insurance</h2>
          <div className="cards">
            {policies.map((policy) => (
              <PolicyCard
                key={policy.slug}
                policy={policy}
                selected={selected.includes(policy.slug)}
                onToggle={() => toggle(policy.slug)}
              />
            ))}
          </div>
        </section>
      ))}

      {selected.length >= 2 && !comparison && (
        <button className="compare-btn" onClick={() => void compare()}>
          Compare selected ({selected.length})
        </button>
      )}
      {error && <p className="exclusions">{error}</p>}
      {comparison && <ComparisonTable comparison={comparison} />}

      <p className="disclaimer">
        Information only, not insurance advice. Confirm final terms with the insurer.
      </p>
    </div>
  );
}
