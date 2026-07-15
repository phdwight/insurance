import { useState } from "react";
import {
  fetchComparison,
  type Comparison,
  type MatchReason,
  type Recommendation,
  type Recommendations,
} from "../api";
import BrochurePanel from "./BrochurePanel";

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

// The writer classifies each reason as "match" or "gap"; normalize here so a
// plain string (older payload / guided-mode fallback) is treated as a match.
function normalizeReason(reason: MatchReason | string): MatchReason {
  if (typeof reason === "string") return { text: reason, kind: "match" };
  return { text: reason.text, kind: reason.kind === "gap" ? "gap" : "match" };
}

const NOT_SPEC = "Not specified";

function titleCase(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

// Up to three concise facts from the coverage JSON, per product line — they
// render as a stat row, so values are kept short (long free text is trimmed,
// and a maturity sentence is reduced to its "N% of face" gist when present).
function coverageStats(
  line: string,
  coverage: Record<string, unknown> | null | undefined,
): { label: string; value: string }[] {
  const cov = coverage ?? {};
  const str = (v: unknown): string | null => (clean(v) ? String(v).trim() : null);
  const cap = (v: unknown): string | null => (str(v) ? titleCase(str(v)!) : null);
  const years = (v: unknown): string | null =>
    Array.isArray(v) && v.length ? `${v.join(", ")} year${v.length === 1 && v[0] === 1 ? "" : "s"}` : null;
  const maturity = (v: unknown): string | null => {
    const t = str(v);
    if (!t) return null;
    const pct = t.match(/(\d+)\s*%\s*of\s*(?:the\s*)?face/i);
    return pct ? `${pct[1]}% of face` : t.length > 26 ? `${t.slice(0, 24)}…` : t;
  };
  const rows: { label: string; value: string | null }[] =
    line === "travel"
      ? [
          { label: "Medical limit", value: str(cov.medical_limit) },
          { label: "Trip days", value: str(cov.max_trip_days) },
          { label: "Cancellation", value: str(cov.trip_cancellation_limit) },
        ]
      : line === "health"
        ? [
            { label: "Annual limit", value: str(cov.annual_limit) },
            { label: "Room & board", value: str(cov.room_and_board_limit_per_day) },
            { label: "Plan", value: cap(cov.plan_type) },
          ]
        : line === "pet"
          ? [
              { label: "Species", value: cap(cov.species) },
              { label: "Vet fee limit", value: str(cov.vet_fee_annual_limit) },
              { label: "Waiting period", value: str(cov.waiting_period_days) },
            ]
          : [
              { label: "Type", value: cap(cov.policy_type) },
              { label: "Term", value: years(cov.term_years_options) },
              { label: "Maturity benefit", value: maturity(cov.maturity_benefit) },
            ];
  return rows.map((r) => ({ label: r.label, value: r.value ?? NOT_SPEC }));
}

function PolicyCard(props: {
  policy: Recommendation;
  line: string;
  selected: boolean;
  onToggle: () => void;
}) {
  const { policy } = props;
  const reasons = (policy.match_reasons ?? []).map(normalizeReason);
  const strong = policy.match_strength
    ? policy.match_strength === "strong"
    : reasons.length > 0 && !reasons.some((reason) => reason.kind === "gap");
  const stats = coverageStats(props.line, policy.coverage);
  const hasPremium = policy.premium_min != null || policy.premium_max != null;
  return (
    <article className={`policy-card ${props.selected ? "selected" : ""}`}>
      <div className="policy-main">
        <header>
          <div className="policy-title">
            <h3>{policy.name}</h3>
            <p className="insurer">{clean(policy.insurer_name) ?? "Insurer not specified"}</p>
          </div>
          <label className="compare-pick">
            <input type="checkbox" checked={props.selected} onChange={props.onToggle} />
            compare
          </label>
        </header>

        <p className={`match-badge ${strong ? "strong" : "partial"}`}>
          <span className="badge-pill">
            <span className="dot" />
            {strong ? "Strong match" : "Partial match"}
          </span>
          <span className="match-note">
            {strong ? "meets all specified criteria" : "missing key details"}
          </span>
        </p>

        <dl className="stat-row">
          {stats.map((stat) => (
            <div key={stat.label} className="stat">
              <dt>{stat.label}</dt>
              <dd className={stat.value === NOT_SPEC ? "muted" : ""}>{stat.value}</dd>
            </div>
          ))}
        </dl>

        {hasPremium && (
          <p className="premium">
            {peso(policy.premium_min)} – {peso(policy.premium_max)}
            {policy.premium_frequency && (
              <span className="freq">
                {" "}
                {policy.premium_frequency === "single" ? "one-time" : policy.premium_frequency}
              </span>
            )}
          </p>
        )}

        <ul className="reasons">
          {reasons.map((reason, index) => {
            const gap = reason.kind === "gap";
            return (
              <li key={index} className={gap ? "gap" : "ok"}>
                <span className="reason-icon" aria-hidden="true">
                  {gap ? "!" : "✓"}
                </span>
                {reason.text}
              </li>
            );
          })}
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
      </div>

      <BrochurePanel slug={policy.slug} />
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
                line={line}
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
