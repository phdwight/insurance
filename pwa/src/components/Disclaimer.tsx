import { useEffect, useRef, useState } from "react";

/** The legal notice, opened from the footer link.
 *
 *  Canonical wording lives in docs/disclaimer.md and is mirrored here and in
 *  the reviewer portal (ingestion/.../admin.html); tests/test_disclaimer_sync.py
 *  fails the build if a required clause goes missing from either surface. */
export default function Disclaimer() {
  const [open, setOpen] = useState(false);
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <>
      <button type="button" className="disclaimer-link" onClick={() => setOpen(true)}>
        Important disclaimer
      </button>

      <dialog ref={dialogRef} className="disclaimer-dialog" onClose={() => setOpen(false)}>
        <article>
          <h2>Important disclaimer</h2>

          <h3>Information only — not advice</h3>
          <p>
            This service provides general product information and comparisons drawn from
            publicly available insurer materials. It is <strong>not financial, insurance,
            investment, legal, or tax advice</strong>, and it is not a recommendation to buy,
            hold, or cancel any policy. Nothing here is tailored to your personal
            circumstances.
          </p>

          <h3>We are not a licensed insurance intermediary</h3>
          <p>
            The operator is <strong>not</strong> an insurance company, agent, broker, or
            adviser, and is <strong>not licensed by the Philippine Insurance Commission</strong>{" "}
            or any other regulator to sell or advise on insurance. This service does not
            solicit, negotiate, quote, bind, issue, or sell insurance, and it does not receive
            commissions for doing so. Using it creates no agency, brokerage, fiduciary, or
            professional-client relationship of any kind.
          </p>

          <h3>Consult a licensed professional</h3>
          <p>
            Before buying, changing, or cancelling any policy, speak with a{" "}
            <strong>licensed insurance agent, broker, or financial adviser</strong>, and read
            the insurer's official policy contract. Only the insurer can quote you, assess
            your eligibility, and issue cover.
          </p>

          <h3>Accuracy is not guaranteed — the insurer's contract governs</h3>
          <p>
            Policy details are extracted from insurer brochures and may be{" "}
            <strong>incomplete, outdated, or wrong</strong>. Products, premiums, and
            eligibility change without notice. Parts of this service use{" "}
            <strong>artificial intelligence, which can make mistakes</strong> or produce
            inaccurate summaries. Always verify every detail directly with the insurer. Where
            anything here conflicts with the insurer's official policy contract, the{" "}
            <strong>policy contract prevails</strong>.
          </p>

          <h3>Provided "as is"</h3>
          <p>
            This service is provided <strong>"as is" and "as available", without warranties
            of any kind</strong>, whether express, implied, or statutory — including any
            implied warranty of merchantability, fitness for a particular purpose, title,
            non-infringement, accuracy, completeness, or uninterrupted or error-free
            operation.
          </p>

          <h3>Limitation of liability</h3>
          <p>
            To the maximum extent permitted by law, the operator and its contributors are{" "}
            <strong>not liable for any loss or damage</strong> — direct, indirect, incidental,
            consequential, special, exemplary, or punitive — arising from your use of, or
            reliance on, this service. That includes lost profits, lost savings, lost or
            denied insurance coverage, a declined or reduced claim, data loss, and business
            interruption, even if advised of the possibility. Your decisions, and their
            consequences, are your own.
          </p>

          <h3>No affiliation with insurers</h3>
          <p>
            The operator is <strong>not affiliated with, endorsed by, or acting on behalf
            of</strong> any insurer named in this service. Product and company names are the
            trademarks of their respective owners and are used only to identify the products
            described.
          </p>

          <h3>Your information</h3>
          <p>
            Answers you give are used only to filter the policy catalog during your session
            and are deleted on a routine schedule. Do not enter information you would not want
            stored. This notice is not a privacy policy.
          </p>

          <h3>Changes</h3>
          <p>This service and this notice may change at any time without notice.</p>
        </article>
        <form method="dialog" className="disclaimer-close">
          <button type="submit">Close</button>
        </form>
      </dialog>
    </>
  );
}
