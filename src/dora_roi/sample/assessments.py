"""Sample Art. 30 contract assessments for the fictional Alpenrand group.

Thirteen arrangements are assessed, showing the gaps typically found when pre-DORA contracts
are reviewed: missing exit provisions (Helix core banking, Mobilio), no audit rights
(Ledgerline, Wealthbridge), no subcontracting conditions (Ledgerline, Cirrus), and no TLPT
participation clause for critical services (Cirrus, Helix, Ledgerline, Mobilio). Two
call-offs under the Nimbus master agreement inherit its assessment; one assessment is still
in progress; several contracts, including critical ones, are not assessed yet.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from dora_roi.contracts.model import AssessmentBook, ContractAssessment, ProvisionStatus
from dora_roi.contracts.provisions import PROVISIONS, Scope
from dora_roi.contracts.suggest import suggest
from dora_roi.model import RegisterOfInformation
from dora_roi.sample.contract_docs import (
    SAMPLE_CONTRACT_NAME,
    SAMPLE_CONTRACT_REF,
    SAMPLE_CONTRACT_TEXT,
)

ASSESSOR = "GRC Advisory (sample)"
_NON_CRITICAL = {"AR-DE-0064", "AR-DE-0061"}
P, PA, M = ProvisionStatus.PRESENT, ProvisionStatus.PARTIAL, ProvisionStatus.MISSING

#: Evidence for "present" items that need no specific note.
_DEFAULT_CLAUSES = {
    "30.1": ("Clause 1 / entire agreement", "Single agreement incl. schedules and SLA."),
    "30.2.a.1": ("Schedule 1", "Statement of work lists the services."),
    "30.2.a.2": ("Clause 9", "Prior written consent for subcontracting; flow-down of terms."),
    "30.2.b.1": ("Schedule 5", "Service and data locations listed."),
    "30.2.b.2": ("Clause 9.4", "Six months' advance notice of location changes."),
    "30.2.c": ("Clause 11", "Confidentiality, integrity, availability, authenticity; DPA."),
    "30.2.d": ("Clause 18.3", "Data return in machine-readable format, also on insolvency."),
    "30.2.e": ("Schedule 2", "SLA with annual review."),
    "30.2.f": ("Clause 12.2", "Incident assistance included in the fees."),
    "30.2.g": ("Clause 15", "Cooperation with competent and resolution authorities."),
    "30.2.h": ("Clause 17", "Termination rights per Art. 28(7); 12 months' notice."),
    "30.2.i": ("Clause 13.4", "Participation in awareness and resilience training."),
    "30.3.a": ("Schedule 2", "99.9 % availability, response/resolution times, service credits."),
    "30.3.b": ("Clause 14", "Monthly reporting; notification of material developments."),
    "30.3.c": ("Clause 12.5", "BCP/DR tested annually; ISO/IEC 27001 controls."),
    "30.3.d": ("Clause 16.3", "Participation in the bank's TLPT, incl. pooled TLPT."),
    "30.3.e.i": ("Clause 16.1", "Unrestricted access, inspection and audit rights incl. the "
                 "competent authority."),
    "30.3.e.ii": ("Clause 16.2", "Pooled audits / SOC 2 Type II as alternative assurance."),
    "30.3.e.iii": ("Clause 16.4", "Full cooperation in on-site inspections incl. Lead "
                   "Overseer."),
    "30.3.e.iv": ("Clause 16.5", "Audit plan with scope, procedure and frequency."),
    "30.3.f.i": ("Clause 19.1", "24-month transition period at contract terms."),
    "30.3.f.ii": ("Clause 19.2", "Migration assistance to a successor or in-house."),
}

#: contract ref → (assessed on, document, notes, {provision: (status, clause, evidence)}).
#: Provisions not listed are "present" with the default clause; ``None`` = not assessed.
Spec = dict[str, tuple[ProvisionStatus, str, str] | None]

_SAMPLES: tuple[tuple[str, date, str, str, Spec], ...] = (
    ("MSA-DE-0001", date(2025, 10, 14), "Nimbus Cloud Services Agreement + DORA Addendum v2.pdf",
     "Hyperscaler standard terms with the provider's financial-services DORA addendum. "
     "Call-offs CO-LU-0002 and CO-AT-0003 rely on these terms.", {
         "30.3.d": (PA, "Addendum 7", "Participation only in pooled TLPT, at the provider's "
                    "discretion and with 6 months' notice."),
         "30.3.e.i": (PA, "Addendum 4.1", "Audit rights for the bank and the competent "
                      "authority, but on-site access only to 'shared-responsibility' "
                      "documentation; no right to take copies."),
         "30.3.f.i": (PA, "Clause 22.4", "Transition period of 90 days only – too short for "
                      "the core-banking hosting migration (exit plan assumes 18 months)."),
     }),
    ("MSA-DE-0010", date(2025, 10, 21), "Cirrus Online Services Terms (Oct 2024).pdf",
     "SaaS terms for workplace, CRM and security operations tooling.", {
         "30.2.a.2": (PA, "Clause 6.3", "General authorisation of sub-processors with a public "
                      "list; no conditions for services supporting critical functions and no "
                      "right to object."),
         "30.3.d": (M, "", "No TLPT clause; penetration testing by customers is prohibited "
                    "without the provider's consent (clause 8.7)."),
     }),
    ("AR-DE-0022", date(2025, 9, 30), "Helix Licence and Services Agreement 2016.pdf",
     "Core-banking licence signed in 2016, amended 2019; not yet renegotiated for DORA.", {
         "30.2.f": (PA, "Clause 10.2", "Incident support billed on time and material at "
                    "rates 'applicable at the time'."),
         "30.2.i": (M, "", "No reference to security awareness or resilience training."),
         "30.3.b": (PA, "Clause 8", "Quarterly reports; no obligation to notify material "
                    "developments."),
         "30.3.d": (M, "", "No TLPT participation clause."),
         "30.3.e.ii": (M, "", "Not addressed."),
         "30.3.f.i": (M, "", "No exit or transition provisions; licence ends at termination."),
         "30.3.f.ii": (M, "", "No migration assistance; source code escrow only."),
     }),
    ("AR-DE-0026", date(2025, 10, 2), "Ledgerline SaaS Agreement 2021.docx",
     "Payment hub SaaS hosted on Nimbus (rank 2) – the subcontracting is not covered by the "
     "contract.", {
         "30.2.a.2": (M, "", "Silent on subcontracting although the service is hosted by "
                      "Nimbus Cloud Services EMEA."),
         "30.2.b.2": (M, "", "No obligation to notify location changes."),
         "30.3.d": (M, "", "No TLPT clause."),
         "30.3.e.i": (M, "", "No audit or access rights; only an annual ISAE 3402 report."),
         "30.3.e.ii": (P, "Clause 14", "ISAE 3402 Type II report provided annually."),
         "30.3.e.iii": (M, "", "No cooperation obligation for inspections."),
         "30.3.e.iv": (M, "", "Not addressed."),
     }),
    (SAMPLE_CONTRACT_REF, date(2025, 11, 4), SAMPLE_CONTRACT_NAME,
     "Assessed from the uploaded contract; keyword suggestions reviewed clause by clause.", {
         "30.1": (P, "15.1", "Entire agreement incl. schedules and SLA; written amendments."),
         "30.2.a.1": (P, "2.1", "Statement of Work in Schedule 1."),
         "30.2.a.2": (P, "3", "Prior written consent; provider remains responsible."),
         "30.2.b.1": (P, "4.1", "Austria/Germany; data in German data centres."),
         "30.2.b.2": (P, "4.2", "Six months' advance notice."),
         "30.2.c": (P, "5.1", "All four protection goals; GDPR DPA (Schedule 3)."),
         "30.2.d": (P, "14.1", "Return within 30 days, also on insolvency."),
         "30.2.e": (P, "6", "SLA in Schedule 2, reviewed annually."),
         "30.2.f": (P, "7.1", "Assistance at no additional cost."),
         "30.2.g": (P, "10.1", "Cooperation with competent and resolution authorities."),
         "30.2.h": (P, "13", "12 months' notice; Art. 28(7) circumstances listed."),
         "30.2.i": (P, "11.1", "Participation where reasonably requested."),
         "30.3.a": (P, "6", "99.9 %, 30-minute response time, service credits."),
         "30.3.b": (P, "8", "Monthly reports; notification of material developments."),
         "30.3.c": (P, "9", "BCP/DR tested annually; ISO/IEC 27001."),
         "30.3.d": (M, "", "No TLPT clause (only the provider's own penetration tests, 5.2)."),
         "30.3.e.i": (PA, "12", "Audit by the bank only, once a year, 30 days' notice; no "
                      "rights for the competent authority; no on-site copies."),
         "30.3.e.ii": (M, "", "Not addressed."),
         "30.3.e.iii": (M, "", "No cooperation obligation for inspections."),
         "30.3.e.iv": (PA, "12.1", "Frequency defined; scope and procedure not defined."),
         "30.3.f.i": (M, "", "No transition period – the provider may stop at termination."),
         "30.3.f.ii": (PA, "14.2", "Migration cooperation only at then-current rates; no "
                       "obligation to continue the service during migration."),
     }),
    ("AR-DE-0030", date(2025, 10, 9), "CardStream Processing Agreement 2024.pdf",
     "Renegotiated in 2024 using the bank's DORA contract template.", {}),
    ("AR-DE-0039", date(2025, 10, 16), "TreasuryOne Subscription Agreement 2025.pdf",
     "Signed in 2025 on the bank's DORA template.", {}),
    ("AR-DE-0014", date(2025, 9, 25), "Intra-group SLA Alpenrand Services 2023.docx",
     "Intra-group shared-service agreement with the Swiss service company.", {
         "30.2.h": (PA, "Clause 9", "Ordinary termination only; Art. 28(7) termination "
                    "circumstances not provided for."),
     }),
    ("AR-DE-0064", date(2025, 10, 28), "PeopleLedger HR Cloud Terms.pdf",
     "HR and payroll SaaS (not critical): Art. 30(2) review only.", {
         "30.2.b.2": (M, "", "Locations may be changed by the provider without notice."),
         "30.2.i": (M, "", "Not addressed."),
     }),
    ("AR-DE-0061", date(2025, 10, 29), "CustomerSphere Master Subscription Agreement.pdf",
     "CRM SaaS (not critical), US provider.", {
         "30.2.b.1": (PA, "Clause 7", "Data 'in the EU or the US' – no specific countries."),
         "30.2.d": (PA, "Clause 12.4", "Data export only within 30 days after termination; "
                    "insolvency and resolution not covered."),
         "30.2.g": (M, "", "No cooperation with authorities beyond legal compulsion."),
     }),
    ("AR-LU-0049", date(2025, 10, 7), "Wealthbridge Platform Agreement (LU) 2020.pdf",
     "Portfolio management platform of the Luxembourg private bank.", {
         "30.3.e.i": (M, "", "Explicitly no audit rights ('the customer relies on the "
                      "provider's SOC 1 report')."),
         "30.3.e.iii": (M, "", "No cooperation obligation for inspections."),
         "30.3.f.i": (PA, "Clause 20", "Transition period of 6 months, at the provider's "
                      "then-current rates."),
     }),
    ("AR-AT-0048", date(2025, 11, 3), "Fundcalc Administration Agreement 2022.pdf",
     "Assessment in progress – Art. 30(3) review scheduled with the provider.", {
         **{p.id: None for p in PROVISIONS if p.scope is Scope.CRITICAL},
     }),
    ("AR-LU-0016", date(2025, 9, 26), "Intra-group SLA Alpenrand Services (LU) 2023.docx",
     "Same template as AR-DE-0014.", {
         "30.2.h": (PA, "Clause 9", "Ordinary termination only; Art. 28(7) termination "
                    "circumstances not provided for."),
     }),
)


def sample_assessments(register: RegisterOfInformation | None = None) -> AssessmentBook:
    """The sample assessment book (only arrangements present in ``register`` if given)."""
    known = {c.contract_ref for c in register.b_02_01} if register is not None else None
    book = AssessmentBook()
    for ref, when, document, notes, spec in _SAMPLES:
        if known is not None and ref not in known:
            continue
        a = ContractAssessment(contract_ref=ref, assessor=ASSESSOR, assessed_on=when,
                               document=document, notes=notes)
        for p in PROVISIONS:
            if p.id in spec:
                entry = spec[p.id]
                if entry is None:
                    continue
                status, clause, evidence = entry
                a.set(p.id, status, clause, evidence)
            elif p.scope is Scope.ALL or ref not in _NON_CRITICAL:
                clause, evidence = _DEFAULT_CLAUSES[p.id]
                a.set(p.id, P, clause, evidence)
        if ref == SAMPLE_CONTRACT_REF:  # reviewed keyword suggestions (audit trail)
            suggested = suggest(SAMPLE_CONTRACT_TEXT).by_id()
            for pid, item in a.items.items():
                item.suggested_status = suggested[pid].suggestion.status
        at = datetime(when.year, when.month, when.day, 16, 0, tzinfo=UTC)
        book.save(a, by=ASSESSOR, at=at)
    return book
