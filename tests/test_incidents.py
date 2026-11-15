"""Major ICT-related incident classification, reporting deadlines, recurring incidents, log."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from click.testing import CliRunner

from dora_roi.cli import main
from dora_roi.incidents import (
    DEFAULT_THRESHOLDS,
    Answers,
    Criterion,
    DeadlineState,
    Incident,
    IncidentLog,
    IncidentStatus,
    Outcome,
    ReportKind,
    classify,
    classify_answers,
    criteria,
    recurring_groups,
    timeline,
)
from dora_roi.incidents.classify import add_months, aggregate
from dora_roi.incidents.criteria import criteria_markdown, criterion_info
from dora_roi.incidents.deadlines import humanise, next_deadline
from dora_roi.incidents.model import zone
from dora_roi.incidents.report import (
    incident_view,
    overview,
    render_summary_html,
    summary_dict,
    summary_markdown,
)
from dora_roi.io.excel import write_workbook
from dora_roi.model import Branch
from dora_roi.sample import generate_sample
from dora_roi.sample.incidents import sample_incidents

from conftest import ENTITY, PROVIDER, build_valid_register

NOW = datetime(2025, 12, 1, 12, 0, tzinfo=UTC)
KNOWN_NO: dict[str, object] = {
    "malicious_access": False, "clients_affected": 0, "clients_total": 1000,
    "counterparts_affected": 0, "counterparts_total": 10, "relevant_clients": False,
    "transactions_affected": 0, "transactions_daily": 100,
    "transaction_value_affected": Decimal(0), "transaction_value_daily": Decimal(100),
    "media": False, "complaints": False, "regulatory_breach": False, "client_loss": False,
    "duration_hours": 1.0, "downtime_hours": 0.0, "member_states": ["DE"],
    "data_impact": False, "economic_eur": Decimal(0)}


def answers(**overrides: object) -> Answers:
    data: dict[str, object] = {"critical_services": True, **KNOWN_NO}
    data.update(overrides)
    return Answers.model_validate(data)


def incident(iid: str = "INC-1", **kw: object) -> Incident:
    data: dict[str, object] = {"id": iid, "title": "Outage", "detected_at": NOW}
    data.update(kw)
    return Incident.model_validate(data)


# =========================================================================== criteria


def test_criteria_definitions() -> None:
    cs = criteria()
    assert [c.key for c in cs] == list(Criterion)
    for c in cs:
        assert c.title("de") != c.title("en") and c.question("de") and c.threshold("de")
        assert c.dora.startswith("DORA Art. 18(1)")
    assert "100.000" in criterion_info(Criterion.CLIENTS).threshold("de")
    assert "> 2 h" in criterion_info(Criterion.DURATION).threshold("en")
    md = criteria_markdown()
    assert "two or more" in md and "Initial notification" in md and "2025/301" in md


# =========================================================================== classification


@pytest.mark.parametrize(("overrides", "outcome", "basis"), [
    ({"critical_services": False}, Outcome.NOT_MAJOR, "no_critical"),
    ({"malicious_access": True}, Outcome.MAJOR, "malicious"),
    ({"downtime_hours": 2.5, "member_states": ["DE", "AT"]}, Outcome.MAJOR, "thresholds"),
    ({"downtime_hours": 2.5}, Outcome.NOT_MAJOR, "below"),
    ({"downtime_hours": 2.5, "media": None}, Outcome.UNDETERMINED, "open"),
    ({"critical_services": None, "downtime_hours": 3.0, "data_impact": True},
     Outcome.UNDETERMINED, "open"),
])
def test_outcomes(overrides: dict[str, object], outcome: Outcome, basis: str) -> None:
    c = classify_answers(answers(**overrides))
    assert c.outcome is outcome and c.basis == basis
    assert c.major is (outcome is Outcome.MAJOR)
    if outcome is Outcome.UNDETERMINED:
        assert c.open_questions
    else:
        assert c.open_questions == []


def test_all_unknown_lists_open_questions() -> None:
    c = classify_answers(Answers())
    assert c.outcome is Outcome.UNDETERMINED
    qs = c.open_questions
    assert qs[0] == "critical_services" and "malicious_access" in qs and "economic_eur" in qs
    assert c.met_count == 0 and c.possible_count == 6


@pytest.mark.parametrize(("overrides", "criterion", "trigger"), [
    ({"clients_affected": 101, "clients_total": 1000}, Criterion.CLIENTS, "clients_share"),
    ({"clients_affected": 100_001, "clients_total": 10_000_000}, Criterion.CLIENTS,
     "clients_absolute"),
    ({"counterparts_affected": 4, "counterparts_total": 10}, Criterion.CLIENTS,
     "counterparts_share"),
    ({"transactions_affected": 11}, Criterion.CLIENTS, "transactions_share"),
    ({"transaction_value_affected": Decimal(11)}, Criterion.CLIENTS,
     "transaction_value_share"),
    ({"relevant_clients": True}, Criterion.CLIENTS, "relevant_clients"),
    ({"media": True}, Criterion.REPUTATION, "media"),
    ({"client_loss": True}, Criterion.REPUTATION, "client_loss"),
    ({"duration_hours": 24.5}, Criterion.DURATION, "duration"),
    ({"downtime_hours": 2.01}, Criterion.DURATION, "downtime"),
    ({"member_states": ["DE", "LU"]}, Criterion.GEOGRAPHY, "member_states"),
    ({"data_impact": True}, Criterion.DATA, "data_impact"),
    ({"economic_eur": Decimal("100000.01")}, Criterion.ECONOMIC, "economic"),
])
def test_each_threshold_triggers(overrides: dict[str, object], criterion: Criterion,
                                 trigger: str) -> None:
    r = classify_answers(answers(**overrides)).results[criterion]
    assert r.met is True and trigger in [t.key for t in r.triggers]


@pytest.mark.parametrize("overrides", [
    {"clients_affected": 100, "clients_total": 1000},  # exactly 10 % is not "higher than"
    {"downtime_hours": 2.0}, {"duration_hours": 24.0},
    {"economic_eur": Decimal(100_000)}, {"member_states": ["DE", "CH"]},  # CH not an EEA MS
    {"counterparts_affected": 3, "counterparts_total": 10},
])
def test_boundaries_not_met(overrides: dict[str, object]) -> None:
    c = classify_answers(answers(**overrides))
    assert c.met_count == 0 and c.outcome is Outcome.NOT_MAJOR


def test_zero_denominator_is_unknown_and_member_states_normalised() -> None:
    a = answers(clients_total=0, member_states=[" de", "LU", "de", ""])
    assert a.member_states == ["DE", "LU"]
    r = classify_answers(a).results[Criterion.CLIENTS]
    assert r.met is False or r.met is None


def test_duration_from_timestamps_and_ongoing() -> None:
    a = answers(duration_hours=None)
    ongoing = incident(occurred_at=NOW - timedelta(hours=30), detected_at=NOW - timedelta(
        hours=29), answers=a)
    r = classify(ongoing, NOW).results[Criterion.DURATION]
    assert r.met is True and r.triggers[0].value == "30.0 h"
    short = incident(detected_at=NOW - timedelta(hours=5), answers=answers(
        duration_hours=None, media=True))
    c = classify(short, NOW)
    r = c.results[Criterion.DURATION]
    assert r.met is None and "duration_hours" in r.open_questions
    assert c.outcome is Outcome.UNDETERMINED and "duration_hours" in c.open_questions
    quiet = incident(detected_at=NOW - timedelta(hours=5), answers=a)
    assert classify(quiet, NOW).outcome is Outcome.NOT_MAJOR  # one unknown cannot reach two
    done = short.model_copy(update={"resolved_at": NOW - timedelta(hours=1)})
    assert classify(done, NOW).results[Criterion.DURATION].met is False
    assert done.duration_hours(NOW) == (4.0, True)
    assert classify_answers(answers(duration_hours=None)).results[
        Criterion.DURATION].met is None


# =========================================================================== deadlines


def test_timeline_classification_basis_and_states() -> None:
    inc = incident(answers=answers(malicious_access=True),
                   detected_at=NOW - timedelta(hours=3), classified_at=NOW - timedelta(hours=1))
    c = classify(inc, NOW)
    dl = timeline(inc, c, NOW)
    assert [d.kind for d in dl] == list(ReportKind)
    initial, intermediate, final = dl
    assert initial.due == NOW + timedelta(hours=3) and initial.basis == "classification"
    assert initial.state(NOW) is DeadlineState.DUE
    assert intermediate.state(NOW) is DeadlineState.PROJECTED
    assert intermediate.due == initial.due + timedelta(hours=72)
    assert final.due == add_months(intermediate.due, 1)
    assert next_deadline(dl) is initial
    assert initial.state(NOW + timedelta(hours=4)) is DeadlineState.OVERDUE
    sub = inc.model_copy(update={"initial_submitted_at": NOW + timedelta(hours=1),
                                 "intermediate_submitted_at": NOW + timedelta(days=4)})
    dl = timeline(sub, c, NOW)
    assert dl[0].state(NOW) is DeadlineState.DONE
    assert dl[1].due == NOW + timedelta(hours=73) and dl[1].state(NOW) is DeadlineState.LATE
    assert dl[2].due == add_months(NOW + timedelta(days=4), 1) and not dl[2].projected


def test_timeline_awareness_cap_and_unclassified() -> None:
    inc = incident(answers=answers(malicious_access=True), detected_at=NOW - timedelta(hours=22),
                   classified_at=NOW)
    initial = timeline(inc, classify(inc, NOW), NOW)[0]
    assert initial.basis == "awareness" and initial.due == NOW + timedelta(hours=2)
    no_ts = inc.model_copy(update={"classified_at": None, "detected_at": NOW})
    assert timeline(no_ts, classify(no_ts, NOW), NOW)[0].due == NOW + timedelta(hours=4)
    minor = incident(answers=answers())
    assert timeline(minor, classify(minor, NOW), NOW) == []
    assert next_deadline([]) is None


def test_humanise_and_add_months() -> None:
    assert humanise(timedelta(days=2, hours=3, minutes=5)) == "2 d 3 h"
    assert humanise(timedelta(days=-2, hours=3), "de") == "1 T 21 h"
    assert humanise(timedelta(hours=3, minutes=12)) == "3 h 12 min"
    assert humanise(timedelta(minutes=-45)) == "45 min"
    assert add_months(datetime(2024, 1, 31, tzinfo=UTC), 1).day == 29
    assert add_months(datetime(2025, 1, 31, tzinfo=UTC), 1).day == 28
    assert add_months(datetime(2025, 11, 30, tzinfo=UTC), 3) == datetime(2026, 2, 28,
                                                                         tzinfo=UTC)
    assert add_months(datetime(2100, 1, 31, tzinfo=UTC), 1).day == 28


# =========================================================================== recurring


def test_recurring_groups_window_and_aggregation() -> None:
    log = IncidentLog()
    base = answers(clients_affected=60, clients_total=1000, downtime_hours=1.5)
    for iid, when in (("A", NOW - timedelta(days=150)), ("B", NOW - timedelta(days=20)),
                      ("C", NOW - timedelta(days=400))):
        log.save(incident(iid, detected_at=when, resolved_at=when + timedelta(hours=2),
                          recurrence_key="Cert", answers=base), "created")
    log.save(incident("D", recurrence_key="cert ", answers=answers(malicious_access=True)),
             "created")  # major on its own → excluded
    log.save(incident("E", recurrence_key="other", answers=base), "created")
    groups = recurring_groups(log, NOW)
    assert len(groups) == 1
    g = groups[0]
    assert [i.id for i in g.incidents] == ["A", "B"] and g.key == "Cert" and g.major
    assert g.answers.clients_affected == 120 and g.answers.downtime_hours == 3.0
    assert g.answers.duration_hours == 2.0 and g.window_end == add_months(g.window_start, 6)
    assert {r.criterion for r in g.classification.met} == {Criterion.CLIENTS,
                                                           Criterion.DURATION}


def test_aggregate_with_unknowns() -> None:
    a = incident("A", answers=Answers(critical_services=True, member_states=["DE"]))
    b = incident("B", answers=Answers(critical_services=None, member_states=None,
                                      economic_eur=Decimal(5)))
    agg = aggregate([a, b], NOW)
    assert agg.critical_services is True and agg.member_states is None
    assert agg.economic_eur is None and agg.clients_total is None
    assert agg.duration_hours is None  # unresolved → not final


# =========================================================================== model & log


def test_log_ids_history_json_and_timezone() -> None:
    log = IncidentLog(timezone="Europe/Zurich")
    assert log.next_id(datetime(2025, 12, 31, 23, 30, tzinfo=UTC)) == "INC-2026-001"
    log.save(incident("INC-2025-007"), "created", by="me", note="n", at=NOW)
    log.save(incident("INC-2025-x"), "created")
    assert log.next_id(NOW) == "INC-2025-008" and len(log) == 2
    stored = log.save(incident("INC-2025-007", title="Renamed"), "updated")
    assert [e.action for e in stored.history] == ["created", "updated"]
    text = log.to_json()
    again = IncidentLog.from_json(text)
    assert again.get("INC-2025-007") == log.get("INC-2025-007")
    assert again.timezone == "Europe/Zurich"
    with pytest.raises(ValueError, match="incident log"):
        IncidentLog.from_json("{}")
    other = IncidentLog()
    other.save(incident("X"), "created")
    assert log.merge(other) == (1, 0) and len(log) == 3
    log.remove("X")
    log.remove("nope")
    assert log.get("X") is None
    assert zone("No/Such_Zone") is UTC and zone("UTC") is UTC
    assert str(zone("Europe/Berlin")) == "Europe/Berlin"
    naive = incident(detected_at=datetime(2025, 1, 1, 10, 0))
    assert naive.detected_at.tzinfo is UTC
    assert naive.submitted(ReportKind.FINAL) is None
    assert next(i.id for i in log.ordered()) in {"INC-2025-007", "INC-2025-x"}


# =========================================================================== views & reports


def test_incident_view_links_and_states() -> None:
    reg = build_valid_register()
    reg.add(Branch(branch_code="BR-1", head_office_lei=ENTITY, name="Milano", country="IT"))
    inc = incident(provider_codes=[PROVIDER, "UNKNOWN"], contract_refs=["C-001", "C-404"],
                   entity_leis=[ENTITY, "X"], answers=answers(malicious_access=True))
    v = incident_view(inc, reg, NOW)
    assert [p.in_register for p in v.providers] == [True, False]
    assert v.providers[0].name == "SaaS Vendor GmbH"
    assert [c.in_register for c in v.contracts] == [True, False]
    assert v.entities[0].name == "Test Bank AG" and not v.entities[1].in_register
    assert v.functions[0].critical and v.supports_critical
    assert v.suggested_states == ["DE", "IT"] and v.next is not None
    assert incident_view(inc, None, NOW).providers[0].name == PROVIDER


def test_overview_exports() -> None:
    reg = generate_sample().register
    now = datetime(2026, 2, 1, 9, 0, tzinfo=UTC)
    log = sample_incidents(reg, now)
    ov = overview(log, reg, now)
    counts = ov.counts()
    assert counts == {"total": 5, "open": 1, "major": 1, "undetermined": 0, "overdue": 0,
                      "recurring_major": 1}
    assert [v.incident.id for v in ov.open_major] == ["INC-2026-014"]
    nxt = ov.next_deadline()
    assert nxt is not None and nxt[1].kind is ReportKind.INITIAL
    data = summary_dict(ov, "Europe/Berlin")
    assert data["schema"] == "dora-roi-toolkit/incident-summary/v1"
    major = data["incidents"][0]
    assert major["classification"]["outcome"] == "major"
    assert major["classification"]["criteria"]["duration"]["triggers"][0]["threshold"] == \
        "downtime"
    assert major["reporting"][0]["state"] == "due"
    assert "F-DE-01" in major["critical_functions"]
    assert data["recurring"][0]["classification"]["outcome"] == "major"
    json.dumps(data)
    md = summary_markdown(ov, "de")
    assert "Wiederkehrende Vorfälle" in md and "Erstmeldung" in md
    html = render_summary_html(ov, client="Alpenrand", timezone="Europe/Berlin")
    assert "INC-2026-014" in html and "Initial notification" in html and "Alpenrand" in html
    assert "Recurring incidents" in html
    late = overview(log, reg, now + timedelta(hours=10))
    assert late.counts()["overdue"] == 1
    assert "Überfällig" in render_summary_html(late, lang="de")


def test_sample_incidents_without_register_links() -> None:
    log = sample_incidents(build_valid_register(), NOW)
    assert all(not i.provider_codes and not i.contract_refs for i in log.incidents.values())
    assert len(log) == 5


# =========================================================================== CLI


def test_cli_incidents(tmp_path: Path) -> None:
    runner = CliRunner()
    reg = tmp_path / "s.xlsx"
    r = runner.invoke(main, ["sample", str(reg), "--incidents", str(tmp_path / "i.json")])
    assert r.exit_code == 0, r.output
    log = str(tmp_path / "i.json")
    r = runner.invoke(main, ["incidents", "summary", log, "--register", str(reg)])
    assert r.exit_code == 0 and "major" in r.output and "recurring kronos" in r.output
    for name in ("s.html", "s.json", "s.md"):
        r = runner.invoke(main, ["incidents", "summary", log, "-o", str(tmp_path / name),
                                 "--lang", "de", "--client", "Alpenrand"])
        assert r.exit_code == 0, r.output
    assert json.loads((tmp_path / "s.json").read_text())["counts"]["major"] == 1
    r = runner.invoke(main, ["incidents", "summary", log, "--now", "2099-01-01T00:00",
                             "--fail-on-overdue"])
    assert r.exit_code == 1 and "overdue" in r.output
    (tmp_path / "bad.json").write_text("[]")
    r = runner.invoke(main, ["incidents", "summary", str(tmp_path / "bad.json")])
    assert r.exit_code == 2
    r = runner.invoke(main, ["incidents", "criteria", "--lang", "de"])
    assert r.exit_code == 0 and "Geografische Ausbreitung" in r.output


def test_cli_summary_with_csv_register(tmp_path: Path) -> None:
    path = write_workbook(build_valid_register(), tmp_path / "r.xlsx")
    log = IncidentLog()
    log.save(incident(provider_codes=[PROVIDER], answers=answers()), "created")
    (tmp_path / "l.json").write_text(log.to_json())
    r = CliRunner().invoke(main, ["incidents", "summary", str(tmp_path / "l.json"),
                                  "--register", str(path), "--now", "2025-12-02"])
    assert r.exit_code == 0 and "not_major" in r.output
    assert DEFAULT_THRESHOLDS.economic_eur == Decimal(100_000)
    assert IncidentStatus("open") is IncidentStatus.OPEN
