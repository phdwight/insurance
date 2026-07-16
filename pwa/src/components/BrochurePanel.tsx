import { useState } from "react";
import { brochureDocUrl, brochureImageUrl } from "../api";

const DocIcon = () => (
  <svg width="26" height="26" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <path
      d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5z"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinejoin="round"
    />
    <path d="M14 3v5h5" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
  </svg>
);

/** Cover-page thumbnail for a policy's brochure, leveled beside the premium +
 *  reasons row. Clicking opens the full document. Falls back to a labelled
 *  placeholder slot when no public brochure exists. */
export default function BrochurePanel({ slug }: { slug: string }) {
  const img = brochureImageUrl(slug);
  const doc = brochureDocUrl(slug);
  const [failed, setFailed] = useState(false);

  if (!img || failed) {
    return (
      <div className="brochure brochure-empty">
        <DocIcon />
        <span>Brochure cover</span>
      </div>
    );
  }

  return (
    <a className="brochure" href={doc ?? img} target="_blank" rel="noreferrer" title="Open brochure">
      <img src={img} alt={`${slug} brochure cover`} loading="lazy" onError={() => setFailed(true)} />
    </a>
  );
}
