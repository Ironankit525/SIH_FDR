# Demonstration walkthrough

Start `python3 scripts/dev.py` and open http://localhost:5173. Every account uses the configured demo password (default `DemoFlow2026!`). Use the sign-out icon to switch roles. The seed is idempotent; reset instructions are in README.

## 1. Correct submission

1. Sign in as `institution@demo.local`; open `DF-<year>-000001` / `MATCH-001`.
2. Open Documents and preview the fictional receipt.
3. Open Evidence comparison: submitted and extracted fields agree. Confidence is a parser estimate.
4. Sign in as `officer@demo.local`, open the case, and Assign to me.
5. Under Bank verification, Run mock verification. The result is **SIMULATED / MOCK BANK DATA**, and the instrument becomes `Mock Confirmed`, never `Officially Confirmed`.
6. Review tasks still include illustrative-rule applicability and the original verification task until the officer records reasoned resolutions.

To demonstrate creation from scratch, use New deposit, enter a unique reference, save the draft, upload a receipt, review extracted details and submit. Fictional sample PDFs are generated in `demo-data/` at seeding time. A newly invented reference is intentionally unknown to the mock bank unless a matching fictional fixture is explicitly added by a developer.

## 2. Insufficient amount

Open `SHORT-002` / `DF-<year>-000002`. The configured illustrative Engineering requirement is ₹35 lakh, while the submitted and extracted amount is ₹15 lakh. The review task explains the amount shortfall and identifies the configured rule as its source. No fraud finding is made.

An institution can respond to the task and add supporting documents. An assigned officer can request clarification, allowing submitted details to be corrected; any correction resets bank verification. Only the officer can resolve the task, with a recorded reason.

## 3. Unconfirmed receipt

Open `UNKNOWN-003` / `DF-<year>-000003` as the verification officer and claim it. Run the mock adapter. Its original document parses correctly, but the fictional bank dataset has no matching reference. The finding is inconclusive and explicitly says this is not proof of fraud. Use the manual verification path to demonstrate how authorised external confirmation would be recorded separately.

Additional deterministic fixtures: `AMOUNT-007` has a different bank amount; `NAME-008` a different depositor; `UNAVAILABLE-009` simulates an unavailable response.

## 4. Upcoming maturity

`MATURITY-004` / `DF-<year>-000004` matures seven days after seeding. Open Maturity & renewals and Notifications. The notification records the deadline and the development email-outbox status.

As an officer or administrator, run Check deadlines / Run deadline monitor. Rerunning at the same reminder stage creates no duplicate notification. Bank maturity, regulatory end and renewal action dates remain distinct in the case detail.

## 5. Renewal and retained evidence

Open `RENEWED-005` / `DF-<year>-000005`, History & renewals. Both `ORIGINAL-005` and `RENEWED-005` are retained, linked by the replacement record; both PDFs remain in Documents.

To perform a fresh replacement, use Renew / replace on another submitted case without a release workflow. Enter a new unique instrument number, amount/dates and reason. Upload the replacement receipt and resubmit. The prior instrument and its evidence remain available; previous bank verification does not carry over.

## 6. Blocked release, clearance and final outcome

1. Sign in as `authority@demo.local` and open Release requests. `DF-<year>-000006` is the seeded release case.
2. PGRC is approved; Vigilance is pending. Supporting documents and the completed illustrative regulatory period are already present. Review tasks have explicit fictional officer resolutions. The demo workflow accepts its separately labelled mock confirmation.
3. Choose Record final decision → Approved and enter notes. The server rejects the action with `Vigilance clearance is pending`.
4. Sign in as `clearance@demo.local`: that user cannot decide the Vigilance cell.
5. Sign in as `vigilance@demo.local` and approve the assigned Vigilance clearance with notes.
6. Return as `authority@demo.local`, review the full case, and approve. The case becomes `Release Authorised`.
7. Record a fictional NOC/completion reference. It becomes `Released`; no funds are moved by the software.
8. View History & renewals or Audit trail for actor-attributed events.

## Administration checks

- Propose a rule version as `admin@demo.local`. The same account cannot approve it. Sign in manually as `admin2@demo.local` to approve.
- Changes to workflow settings apply to new release requests. Existing requests preserve their prerequisites.
- The auditor can inspect evidence and export audit history, but cannot verify, resolve, clear or approve.
- Sign in as the second institution: the first institution's records and documents are inaccessible, even with copied URLs.
