"""Sample ICT-related incidents for the fictional Alpenrand group.

* a **major** incident that is still open – a Nimbus EMEA cloud-region outage taking down
  core banking and payments – detected a few hours before ``now`` so that the reporting
  countdown is live in a demo;
* two **non-major** incidents – a contained phishing campaign (no critical services) and a
  delayed regulatory-reporting batch (critical service, no threshold met);
* a **recurring** series – two short outages of the Kronos SEPA instant gateway caused by
  the same expired-certificate problem, each below the thresholds but major together.

Providers, arrangements and entities are looked up in the register by name/reference, so the
incidents link to whatever register the sample is loaded into (missing links are dropped).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from dora_roi.incidents.model import (
    Answers,
    Incident,
    IncidentLog,
    IncidentStatus,
    RootCause,
)
from dora_roi.model import RegisterOfInformation
from dora_roi.sample.catalogue import ENTITIES

OWNER = "ICT Risk – Incident Management (sample)"


def _ids(register: RegisterOfInformation, providers: tuple[str, ...], contracts: tuple[str, ...],
         entities: tuple[str, ...]) -> dict[str, list[str]]:
    by_name = {p.legal_name: p.provider_code for p in register.b_05_01
               if p.legal_name and p.provider_code}
    refs = {c.contract_ref for c in register.b_02_01}
    names = {e.key: e.name for e in ENTITIES}
    leis = {e.name: e.lei for e in register.b_01_02 if e.name and e.lei}
    return {
        "providers": [by_name[n] for n in providers if n in by_name],
        "contracts": [r for r in contracts if r in refs],
        "entities": [leis[names[k]] for k in entities if names.get(k) in leis],
    }


def sample_incidents(register: RegisterOfInformation, now: datetime | None = None
                     ) -> IncidentLog:
    """The sample incident log; the open major incident is placed relative to ``now``."""
    now = (now or datetime.now(UTC)).astimezone(UTC).replace(second=0, microsecond=0)
    log = IncidentLog()

    def add(incident: Incident, events: list[tuple[datetime, str, str]]) -> None:
        for at, action, note in events:
            log.save(incident, action, by=OWNER, note=note, at=at)

    # ------------------------------------------------------------------ major, live
    links = _ids(register, ("Nimbus Cloud Services EMEA Ltd",),
                 ("MSA-DE-0001", "CO-LU-0002"), ("DE", "LU"))
    detected = now - timedelta(hours=5)
    classified = now - timedelta(hours=1, minutes=30)
    major = Incident(
        id=f"INC-{now.year}-014", title="Nimbus EMEA region outage – core banking and payments "
        "unavailable",
        description="Storage controller failure in the provider's Frankfurt region; the "
                    "core-banking and payment-hub workloads of Alpenrand Bank (Europe) and "
                    "Alpenrand Banque Privée are unavailable, failover to the secondary region "
                    "is in progress.",
        owner=OWNER, occurred_at=detected - timedelta(minutes=20), detected_at=detected,
        classified_at=classified, entity_leis=links["entities"],
        provider_codes=links["providers"], contract_refs=links["contracts"],
        root_cause=RootCause.THIRD_PARTY, recurrence_key="nimbus-fra-storage",
        answers=Answers(
            critical_services=True, malicious_access=False, clients_affected=182_000,
            clients_total=1_250_000, relevant_clients=False, transactions_affected=410_000,
            transactions_daily=1_000_000, media=True, complaints=True,
            regulatory_breach=False, client_loss=False, downtime_hours=4.5,
            member_states=["DE", "FR", "IT", "LU"], data_impact=False,
            economic_eur=Decimal(350_000)))
    add(major, [(detected, "created", "Detected by monitoring; provider status page confirms "
                 "regional incident."),
                (classified, "classified", "Classified as major: critical services, clients, "
                 "downtime, geographical spread, reputation and economic impact.")])

    # ------------------------------------------------------------------ not major (1)
    links = _ids(register, ("Cirrus Platforms Ireland Ltd",), ("MSA-DE-0010",), ("DE",))
    at = datetime(2025, 9, 12, 7, 40, tzinfo=UTC)
    phishing = Incident(
        id="INC-2025-009", title="Phishing campaign against staff mailboxes – contained",
        description="Credential-phishing e-mails to 340 staff; 3 users clicked, no credentials "
                    "used (MFA). Mail filtering rules tightened with the provider.",
        status=IncidentStatus.CLOSED, owner=OWNER, occurred_at=at - timedelta(minutes=35),
        detected_at=at, classified_at=at + timedelta(hours=2),
        resolved_at=at + timedelta(hours=6), entity_leis=links["entities"],
        provider_codes=links["providers"], contract_refs=links["contracts"],
        root_cause=RootCause.MALICIOUS,
        answers=Answers(
            critical_services=False, malicious_access=False, clients_affected=0,
            clients_total=1_250_000, counterparts_affected=0, counterparts_total=420,
            relevant_clients=False, transactions_affected=0, transactions_daily=1_000_000,
            media=False, complaints=False, regulatory_breach=False, client_loss=False,
            downtime_hours=0, member_states=["DE"], data_impact=False,
            economic_eur=Decimal(8_000)))
    add(phishing, [(at, "created", ""), (at + timedelta(hours=2), "classified",
                                         "Not major: no critical services affected."),
                   (at + timedelta(hours=6), "resolved", ""),
                   (at + timedelta(days=3), "closed", "Lessons learned documented.")])

    # ------------------------------------------------------------------ not major (2)
    links = _ids(register, ("RegFlow Reporting S.A.",), ("AR-DE-0054",), ("DE",))
    at = datetime(2025, 10, 30, 22, 15, tzinfo=UTC)
    batch = Incident(
        id="INC-2025-011", title="Regulatory reporting batch delayed (RegFlow)",
        description="Nightly COREP/FINREP data preparation stopped after a failed schema "
                    "update at the provider; rerun completed 9 hours later, before the "
                    "submission deadline.",
        status=IncidentStatus.CLOSED, owner=OWNER, occurred_at=at, detected_at=at,
        classified_at=at + timedelta(hours=3), resolved_at=at + timedelta(hours=9),
        entity_leis=links["entities"], provider_codes=links["providers"],
        contract_refs=links["contracts"], root_cause=RootCause.THIRD_PARTY,
        answers=Answers(
            critical_services=True, malicious_access=False, clients_affected=0,
            clients_total=1_250_000, counterparts_affected=0, counterparts_total=420,
            relevant_clients=False, transactions_affected=0, transactions_daily=1_000_000,
            media=False, complaints=False, regulatory_breach=False, client_loss=False,
            downtime_hours=0, member_states=["DE"], data_impact=False,
            economic_eur=Decimal(4_500)))
    add(batch, [(at, "created", ""), (at + timedelta(hours=3), "classified",
                                      "Not major: critical service, but no threshold met."),
                (at + timedelta(hours=9), "resolved", ""),
                (at + timedelta(days=2), "closed", "")])

    # ------------------------------------------------------------------ recurring pair
    links = _ids(register, ("Kronos Payments B.V.",), ("AR-DE-0028", "AR-LU-0029"),
                 ("DE", "LU"))
    for number, at, downtime, clients in (
            ("INC-2025-006", datetime(2025, 7, 3, 9, 5, tzinfo=UTC), 1.5, 81_000),
            ("INC-2025-012", datetime(2025, 11, 18, 14, 30, tzinfo=UTC), 1.25, 64_000)):
        kronos = Incident(
            id=number, title="SEPA instant payments rejected – Kronos gateway certificate "
            "expired",
            description="Instant credit transfers rejected by the Kronos gateway after an "
                        "expired TLS certificate on the provider side; rotated manually.",
            status=IncidentStatus.CLOSED, owner=OWNER, occurred_at=at, detected_at=at,
            classified_at=at + timedelta(hours=1), resolved_at=at + timedelta(hours=downtime),
            entity_leis=links["entities"], provider_codes=links["providers"],
            contract_refs=links["contracts"], root_cause=RootCause.THIRD_PARTY,
            recurrence_key="kronos-certificate-rotation",
            answers=Answers(
                critical_services=True, malicious_access=False, clients_affected=clients,
                clients_total=1_250_000, counterparts_affected=0, counterparts_total=420,
                relevant_clients=False, transactions_affected=52_000,
                transactions_daily=1_000_000, media=False, complaints=False,
                regulatory_breach=False, client_loss=False, downtime_hours=downtime,
                member_states=["DE"], data_impact=False, economic_eur=Decimal(12_000)))
        add(kronos, [(at, "created", ""), (at + timedelta(hours=1), "classified",
                                           "Not major on its own."),
                     (at + timedelta(hours=downtime), "resolved", ""),
                     (at + timedelta(days=5), "closed", "Provider to automate rotation.")])
    return log
