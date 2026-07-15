import { useState } from "react";
import { brochureDocUrl, brochureImageUrl } from "../api";

const DocIcon = () => (
  <svg width="34" height="34" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <path
      d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5z"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinejoin="round"
    />
    <path d="M14 3v5h5" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
  </svg>
);

/** Cover-page thumbnail for a policy's brochure. Clicking opens the full
 *  document in a new tab. Falls back to a placeholder when no public brochure
 *  exists — the image 404s for policies whose source is a contract (or nothing
 *  shareable), and INGESTION being unset turns the feature off entirely. */
export default function BrochurePanel({ slug }: { slug: string }) {
  const img = brochureImageUrl(slug);
  const doc = brochureDocUrl(slug);
  const [failed, setFailed] = useState(false);

  if (!img || failed) {
    return (
      <div className="brochure brochure-empty">
        <DocIcon />
        <span>No brochure available</span>
      </div>
    );
  }

  return (
    <a className="brochure" href={doc ?? img} target="_blank" rel="noreferrer" title="Open brochure">
      <img
        src={img}
        alt={`${slug} brochure cover`}
        loading="lazy"
        onError={() => setFailed(true)}
      />
    </a>
  );
}
