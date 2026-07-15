/** Start-over control. Icon-only in the composer row, icon+label in the
 *  results view — reachable at the bottom on mobile in either state. */
export default function ResetButton(props: {
  onClick: () => void;
  label?: boolean;
  className?: string;
}) {
  return (
    <button
      type="button"
      className={props.className ?? "composer-reset"}
      onClick={props.onClick}
      aria-label="Start over"
      title="Start over"
    >
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path
          d="M3.5 12a8.5 8.5 0 1 0 2.4-5.9"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
        />
        <path
          d="M3 4v4.5h4.5"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      {props.label && <span>Start over</span>}
    </button>
  );
}
