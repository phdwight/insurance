# Disclaimer — canonical text

**This is the source of record for the legal notice shown to users.** It is
mirrored in two places, which must stay in sync with it:

- `pwa/src/components/Disclaimer.tsx` — the end-user PWA (footer link)
- `ingestion/src/ingestion/admin.html` — the reviewer portal (footer link)

`tests/test_disclaimer_sync.py` fails the build if a required clause goes
missing from any surface.

> **Not legal advice, and not reviewed by counsel.** This wording is a good-faith
> protective baseline drafted by the engineering team. It reduces risk; it does
> not make the operator immune from claims, and it cannot cure a regulatory
> problem — under Philippine law, whether an activity counts as soliciting or
> selling insurance depends on what the product actually does, not on what a
> notice says. Have a Philippine lawyer review this (and a privacy notice) before
> any public launch. See `docs/05-roadmap.md`.

---

## Title

Important disclaimer

## Clauses

### 1. Information only — not advice

This service provides general product information and comparisons drawn from
publicly available insurer materials. It is **not** financial, insurance,
investment, legal, or tax advice, and it is not a recommendation to buy, hold,
or cancel any policy. Nothing here is tailored to your personal circumstances.

### 2. We are not a licensed insurance intermediary

The operator is **not** an insurance company, agent, broker, or adviser, and is
**not licensed by the Philippine Insurance Commission** or any other regulator
to sell or advise on insurance. This service does not solicit, negotiate, quote,
bind, issue, or sell insurance, and it does not receive commissions for doing
so. Using it creates no agency, brokerage, fiduciary, or professional-client
relationship of any kind.

### 3. Consult a licensed professional

Before buying, changing, or cancelling any policy, speak with a **licensed
insurance agent, broker, or financial adviser**, and read the insurer's official
policy contract. Only the insurer can quote you, assess your eligibility, and
issue cover.

### 4. Accuracy is not guaranteed — the insurer's contract governs

Policy details are extracted from insurer brochures and may be **incomplete,
outdated, or wrong**. Products, premiums, and eligibility change without notice.
Parts of this service use **artificial intelligence, which can make mistakes or
produce inaccurate summaries**. Always verify every detail directly with the
insurer. Where anything here conflicts with the insurer's official policy
contract, **the policy contract prevails**.

### 5. Provided "as is"

This service is provided **"as is" and "as available", without warranties of any
kind**, whether express, implied, or statutory — including any implied warranty
of merchantability, fitness for a particular purpose, title, non-infringement,
accuracy, completeness, or uninterrupted or error-free operation.

### 6. Limitation of liability

To the maximum extent permitted by law, the operator and its contributors are
**not liable for any loss or damage** — direct, indirect, incidental,
consequential, special, exemplary, or punitive — arising from your use of, or
reliance on, this service. That includes lost profits, lost savings, lost or
denied insurance coverage, a declined or reduced claim, data loss, and business
interruption, even if advised of the possibility. Your decisions, and their
consequences, are your own.

### 7. No affiliation with insurers

The operator is **not affiliated with, endorsed by, or acting on behalf of** any
insurer named in this service. Product and company names are the trademarks of
their respective owners and are used only to identify the products described.

### 8. Your information

Answers you give are used only to filter the policy catalog during your session
and are deleted on a routine schedule. Do not enter information you would not
want stored. This notice is **not** a privacy policy.

### 9. Changes

This service and this notice may change at any time without notice.

---

## Required phrases (asserted by the sync test)

Each surface must contain, case-insensitively:

- `not financial` — the not-advice clause
- `not licensed by the Philippine Insurance Commission` — the licensing clause
- `licensed insurance agent` — the see-a-professional clause
- `as is` — the no-warranty clause
- `not liable` — the limitation-of-liability clause
- `policy contract prevails` — the insurer-contract-governs clause
