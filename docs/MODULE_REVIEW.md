# Review of the DORA programme modules

The four programme modules – **Art. 30 contract gap analysis**, **major-incident
classification and deadlines**, the **FINMA mapping** and the **readiness dashboard** – were
built without the official texts at hand (originally in pull request #2) and are therefore
labelled **experimental**. This document records the review of each module against the source
texts (November 2026), what was corrected, and what is still open.

The review checks that article numbers, criteria, thresholds and wording match the sources.
It is **not** a legal opinion: before the modules are relied on for a supervisory submission
or a contract negotiation, a DORA/FINMA specialist has to sign off the open items below.

Verdict legend: **verified** – checked against the source and corrected where needed;
**experimental** – usable, but with open items or toolkit methodology that a specialist has to
confirm; **not covered** – outside the module.

## Sources checked

| Module | Sources (versions as published in the Official Journal of the EU / on finma.ch) |
|--------|-------------------------------------------------------------------------------|
| Art. 30 contracts | Regulation (EU) 2022/2554 (DORA) Art. 28–30; Commission Delegated Regulation (EU) 2024/1773 (RTS on the policy for ICT services supporting critical or important functions); Commission Delegated Regulation (EU) 2025/532 (RTS on subcontracting, Art. 30(5)) |
| Incidents | DORA Art. 17–19; Commission Delegated Regulation (EU) 2024/1772 (RTS on classification); Commission Delegated Regulation (EU) 2025/301 (RTS on the content and time limits of reports) |
| FINMA | FINMA Circular 2018/3 "Outsourcing" (version of 4 November 2020); FINMA Circular 2023/1 "Operational risks and resilience – banks"; FINMA Guidance 05/2020, 03/2024, 05/2025; FINMASA Art. 29(2); FINMA list of regulatory projects (1 September 2026) |
| Readiness | DORA (scope Art. 2, chapters II–VI), plus the three modules above |

## Art. 30 contract gap analysis – verdict: checklist verified, coverage experimental

The 22 checklist items and their article references match DORA Art. 30(1)–(3).

Corrected:

- **Keyword hits no longer count as present.** `roi contracts suggest` writes every status as
  *not assessed* and records the heuristic's proposal in `suggested_status` only
  (`apply_suggestions(prefill=False)`); in the workbench the proposal is pre-selected for a
  reviewer who confirms it. "Compliant" is now "All checklist items present", "contract
  compliance" is "Art. 30 clause coverage".
- 30.2.d: data "processed **by** the financial entity" (was "for").
- 30.2.h: text per Art. 30(2)(h) (termination rights and minimum notice periods in accordance
  with the expectations of competent and resolution authorities). The Art. 28(7) termination
  grounds are a separate obligation and are no longer presented as checked by this item.
- 30.3.a: "including updates and revisions thereof … within the agreed service levels".
- 30.3.e.i: on-site copies only "if they are critical to the operations of the ICT third-party
  service provider"; the microenterprise delegation of Art. 30(3), last subparagraph, noted.
  The misplaced Art. 28(6) reference was removed.
- 30.3.e.ii: SOC 1/2, ISAE 3402 and certifications are no longer accepted as standalone
  evidence of alternative assurance (RTS 2024/1773 Art. 8(3)).
- 30.3.f.i: the invented "12–24 months" transition period was removed (DORA sets no length).
- 30.2.a.2 cites Commission Delegated Regulation (EU) 2025/532 as the final RTS.

Open (specialist sign-off needed):

- **A-A30-02** – an arrangement whose function is not yet assessed is treated as *not
  critical*, so the Art. 30(3) items are skipped. Safer: show "criticality unknown" and keep
  the 30(3) items *to assess*.
- **A-A30-03** – Art. 28(7) termination grounds are not a checklist item of their own.
- Contract content required by RTS 2024/1773 (Art. 3(8), 8(2)–(4), 9(1), 10) and RTS
  2025/532 (Art. 4–6) is **not assessed**; Art. 30(4) standard clauses are not assessed
  (A-A30-06).
- The keyword patterns are heuristics; a scanned PDF yields no text (no OCR).

## Incident classification and deadlines – verdict: criteria and thresholds verified, deadlines experimental

The major-incident rule (RTS 2024/1772 Art. 8(1)), the seven criteria and all thresholds,
units and comparison operators of Art. 9(1)–(6) match the Official Journal text.

Corrected:

- **Late classification** (RTS 2025/301 Art. 5(2)): an incident classified as major more than
  24 h after awareness is due 4 h after the classification (was capped at awareness + 24 h).
- **Missing classification time**: the awareness limit applies; the deadline no longer moves
  with "now" every time it is computed.
- **Malicious access** (RTS 2024/1772 Art. 6(c)) now meets the critical-services criterion by
  itself.
- Criterion wording: services requiring "authorisation or registration or supervised by
  competent authorities" (Art. 6(b)); reputational impact "with a material impact on the
  business".
- "Late"/"Overdue" are now "after the conservative deadline", because the weekend and
  bank-holiday relief is not modelled.
- Recurring incidents: results are labelled as the toolkit's aggregation (A-INC-05) and note
  the Art. 8(2) exemption for microenterprises and Art. 16(1) entities.

Open:

- Not modelled: weekend/bank-holiday relief (RTS 2025/301 Art. 5(4)–(6)); updated
  intermediate reports (Art. 5(1)(b)) – the final report is due one month after the recorded
  intermediate report; notice of a delay (Art. 5(3)); reclassification to non-major.
- The Art. 8(2) exemption is a caveat, not an entity flag; the recurring-series rule still
  turns the readiness pillar red for exempt entities.
- No guidance in the form on the economic-impact inclusions/exclusions of Art. 7 or on
  duration estimates (Art. 3(1)).
- **A-INC-05** (aggregation of recurring incidents) and **A-INC-08** (one classification on
  combined group figures) are toolkit methodology.

## FINMA mapping – verdict: experimental

The margin numbers (Rz) were checked against the current versions; neither circular has a
revision on FINMA's list of regulatory projects. The mapping remains an interpretation, not
FINMA guidance.

Corrected:

- Full title and version of Circ. 2018/3; margin numbers cited for every requirement.
- **FIN-OS-02/03/04/14 full → partial**: the inventory of Rz 14 also covers non-ICT
  outsourcings and Swiss entities, which the DORA register does not contain.
- **FIN-OR-02 partial → none**: an RTO is not a tolerance for disruption (Circ. 2023/1 Rz 17;
  Guidance 05/2025 §3.2 rejects deriving tolerances from recovery objectives).
- FIN-OS-07 relabelled to Rz 18–18.1; FIN-OS-09 cites Rz 24–25 and moves confidentiality of
  critical data to Circ. 2023/1 Rz 79/82 (no client-identifying-data rule in 2018/3);
  FIN-OS-13 follows Rz 32–35 (text form, early information on subcontractors and the right to
  terminate – the prior-consent wording was superseded).
- FIN-OR-01 notes that FINMA critical functions (Rz 14–16, 107) are a much narrower set than
  DORA critical or important functions; FIN-OR-07 cites Circ. 2023/1 Rz 60/68/81, FINMASA
  Art. 29(2) and Guidance 05/2020 and 03/2024; FIN-OR-08/10 citations corrected.
- A requirement evidenced by the register only, with nothing applicable to measure (e.g. no
  intra-group arrangements), keeps its design coverage instead of dropping to *none*.

With these corrections the synthetic sample scores **44 %** (0 covered, 21 partly, 3 not
covered) instead of 56 %, and the FINMA pillar of the readiness dashboard turns red.

Open:

- Proportionality by supervisory category (Circ. 2023/1 Rz 20–21) and the institution types
  of Circ. 2018/3 (Rz 5–6.3) are not modelled.
- Not mapped: Circ. 2023/1 Rz 79, 101, 103, 108; Circ. 2018/3 Rz 17 (concentration).
- **A-FINMA-05** – group-level application of Circ. 2018/3 to a Swiss group with EU
  subsidiaries is an interpretation.
- FINMA reporting deadlines are not computed (A-FINMA-04).

## Readiness dashboard – verdict: experimental

The cited DORA articles are correct. The dashboard aggregates the register validation and the
three modules above, so it inherits their open items.

Corrected:

- Renamed "DORA readiness – third parties and incidents", with a scope note on the dashboard
  and in the report: ICT risk management (Art. 5–16), resilience testing (Art. 24–27) and
  information sharing (Art. 45) are **not covered** – it is not an overall DORA assessment.
- "Ready for submission" is now "no blocking errors in the toolkit's validation".
- Third-country concentration includes Switzerland in the DORA view (Art. 29(2)); the FINMA
  view keeps Switzerland apart.
- Notice-period deadlines and the remediation plan are measured from today, not from the
  register's reference date.

Open:

- Concentration thresholds are the toolkit's own method (A-AN-05; DORA sets no caps, cf.
  recital 67) and should be labelled as such on the dashboard.
- Scope rules of DORA Art. 2, simplified frameworks (Art. 16) and microenterprise relief are
  not modelled; entities excluded from the package are not cross-checked against the other
  pillars, and an excluded EU entity raises no warning.

## Next steps

1. Specialist sign-off on the open items above (DORA third-party risk, incident reporting,
   FINMA).
2. Close the "criticality unknown" gap (A-A30-02) and add the Art. 8(2) entity flag – both are
   small code changes once the interpretation is confirmed.
3. Decide whether RTS 2024/1773 and 2025/532 contract content should become checklist items.
