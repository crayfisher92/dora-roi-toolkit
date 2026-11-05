"""DORA readiness of a client: register data quality, Art. 30 contract compliance, incident
management and ICT concentration risk on one page (plus the Swiss/FINMA coverage).

Each *pillar* gets a traffic light (D-064):

* **Register** (Art. 28(3)) – red with more than 10 validation errors, amber with 1–10;
* **Contracts** (Art. 30) – red with high-priority gaps or fewer than half of the arrangements
  supporting critical functions assessed; amber with any gap or assessment outstanding;
* **Incidents** (Art. 17–19) – red with an overdue report or a recurring series meeting the
  major criteria; amber with an open major incident with pending reports or an undetermined
  classification;
* **Concentration** (Art. 28/29) – red/amber with a high/medium-level key message.

Green otherwise; grey when there is nothing to assess (empty register, no incidents
recorded). The overall status is the worst DORA pillar; the FINMA pillar is informational.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any

from markupsafe import Markup

from dora_roi import __version__
from dora_roi.analytics import ConcentrationAnalysis
from dora_roi.analytics.concentration import Level
from dora_roi.contracts.analysis import Portfolio, RemediationPlan, gaps_by_provision
from dora_roi.finma import FinmaView
from dora_roi.i18n import format_date, translator
from dora_roi.incidents.deadlines import DeadlineState, humanise
from dora_roi.incidents.report import IncidentOverview
from dora_roi.quality import QualityScore, Readiness
from dora_roi.reporting.env import environment
from dora_roi.reporting.executive import build_charts, money, pct
from dora_roi.validation import ValidationReport


class Rag(StrEnum):
    RED = "red"
    AMBER = "amber"
    GREEN = "green"
    GREY = "grey"

    @property
    def rank(self) -> int:
        return {"red": 0, "amber": 1, "green": 2, "grey": 3}[self.value]


@dataclass(frozen=True)
class Action:
    priority: str  # high | medium | low
    pillar: str
    text: str
    link: str = ""  # path below the workspace, e.g. "/contracts"


@dataclass
class Pillar:
    key: str  # register | contracts | incidents | concentration | finma
    rag: Rag
    metric: str
    metric_label: str
    lines: list[str] = field(default_factory=list)
    link: str = ""
    article: str = ""


@dataclass
class ReadinessView:
    pillars: list[Pillar]
    actions: list[Action]
    overall: Rag
    generated: datetime
    reference_date: date | None
    entity: str | None
    # inputs, for the detailed report sections
    report: ValidationReport
    quality: QualityScore
    analysis: ConcentrationAnalysis
    portfolio: Portfolio
    plan: RemediationPlan
    incidents: IncidentOverview
    finma: FinmaView | None

    def pillar(self, key: str) -> Pillar:
        return next(p for p in self.pillars if p.key == key)


def _register_pillar(t: Any, q: QualityScore, report: ValidationReport,
                     actions: list[Action]) -> Pillar:
    counts = report.severity_counts()
    rag = {Readiness.READY: Rag.GREEN, Readiness.ALMOST: Rag.AMBER,
           Readiness.NOT_READY: Rag.RED, Readiness.EMPTY: Rag.GREY}[q.readiness]
    lines = [t("rd.reg.status", status=t(f"rd.ready.{q.readiness.value}")),
             t("rd.reg.findings", errors=counts["error"], warnings=counts["warning"],
               records=q.records)]
    if counts["error"]:
        actions.append(Action("high", "register", t("rd.act.fix", n=counts["error"]), "/fix"))
    elif counts["warning"]:
        actions.append(Action("low", "register", t("rd.act.review", n=counts["warning"]),
                              "/fix"))
    return Pillar("register", rag, f"{q.score}/100", t("rd.reg.metric"), lines, "",
                  "DORA Art. 28(3)")


def _contracts_pillar(t: Any, lang: str, pf: Portfolio, plan: RemediationPlan,
                      actions: list[Action]) -> Pillar:
    counts, pc = pf.counts(), plan.counts()
    crit = pf.critical_contracts
    share = pf.critical_assessed_share()
    if not pf.contracts:
        rag = Rag.GREY
    elif pc["high"] or share < 0.5:
        rag = Rag.RED
    elif counts["gaps"] or share < 1:
        rag = Rag.AMBER
    else:
        rag = Rag.GREEN
    lines = [t("rd.c30.assessed", assessed=sum(1 for c in crit if c.assessed), total=len(crit)),
             t("rd.c30.gaps", n=counts["gaps"], missing=pf.total_missing,
               partial=pf.total_partial),
             t("rd.c30.actions", high=pc["high"], medium=pc["medium"], low=pc["low"])]
    top = gaps_by_provision(pf)
    if top:
        worst = max(top, key=lambda x: (x[1], x[2]))
        lines.append(t("rd.c30.top_gap", provision=worst[0].title(lang),
                       n=worst[1] + worst[2]))
    if pc["high"]:
        providers = sorted({i.providers for i in plan.items if i.priority.value == "high"})
        actions.append(Action("high", "contracts", t(
            "rd.act.c30_high", n=pc["high"], providers=", ".join(providers[:3])
            + (" …" if len(providers) > 3 else "")), "/contracts?status=gaps&critical=1"))
    todo = [c for c in crit if not c.assessed]
    if todo:
        actions.append(Action("high" if share < 0.5 else "medium", "contracts",
                              t("rd.act.c30_assess", n=len(todo)),
                              "/contracts?status=not_assessed&critical=1"))
    return Pillar("contracts", rag, f"{share:.0%}", t("rd.c30.metric"), lines, "/contracts",
                  "DORA Art. 30")


def _incidents_pillar(t: Any, ov: IncidentOverview, lang: str,
                      actions: list[Action]) -> Pillar:
    c = ov.counts()
    pending_major = [v for v in ov.views if v.classification.major
                     and any(d.submitted_at is None for d in v.deadlines)]
    recurring = [g for g in ov.recurring if g.major]
    if not ov.views:
        rag = Rag.GREY
    elif c["overdue"] or recurring:
        rag = Rag.RED
    elif pending_major or c["undetermined"]:
        rag = Rag.AMBER
    else:
        rag = Rag.GREEN
    lines = [t("rd.inc.counts", total=c["total"], open=c["open"], major=c["major"])]
    nxt = ov.next_deadline()
    if nxt:
        view, d = nxt
        left = d.due - ov.now
        when = (t("inc.dl.overdue_by", time=humanise(left, lang)) if left.total_seconds() < 0
                else t("inc.dl.in", time=humanise(left, lang)))
        lines.append(t("rd.inc.next", report=t(f"inc.report.{d.kind.value}"),
                       id=view.incident.id, when=when))
        state = d.state(ov.now)
        actions.append(Action(
            "high" if state is DeadlineState.OVERDUE or left.total_seconds() < 86400
            else "medium", "incidents",
            t("rd.act.inc_report", report=t(f"inc.report.{d.kind.value}"),
              id=view.incident.id, when=when), f"/incidents/{view.incident.id}"))
    for g in recurring:
        lines.append(t("rd.inc.recurring", series=g.key, n=len(g.incidents)))
        actions.append(Action("high", "incidents", t("rd.act.inc_recurring", series=g.key),
                              "/incidents"))
    if c["undetermined"]:
        actions.append(Action("medium", "incidents", t("rd.act.inc_classify",
                                                       n=c["undetermined"]), "/incidents"))
    return Pillar("incidents", rag, str(c["major"]), t("rd.inc.metric"), lines, "/incidents",
                  "DORA Art. 17–19")


def _concentration_pillar(t: Any, a: ConcentrationAnalysis, actions: list[Action]) -> Pillar:
    levels = {k.level for k in a.key_findings}
    rag = (Rag.RED if Level.HIGH in levels else Rag.AMBER if Level.MEDIUM in levels
           else Rag.GREEN if a.providers else Rag.GREY)
    single = sum(1 for f in a.critical_functions if f.single_provider)
    lines = [t("rd.conc.top", share=pct(a.top1_share), band=a.hhi_band, hhi=f"{a.hhi:,.0f}"),
             t("rd.conc.cif", n=a.totals.get("critical_functions", 0), single=single),
             t("rd.conc.exit", pct=pct(float(a.totals.get("exit_plan_coverage", 1.0))))]
    for k in a.key_findings:
        if k.level is Level.HIGH:
            actions.append(Action("medium", "concentration", k.title, "/analyse"))
    return Pillar("concentration", rag, pct(a.top1_share), t("rd.conc.metric"), lines,
                  "/analyse", "DORA Art. 28–29")


def _finma_pillar(t: Any, fv: FinmaView, actions: list[Action]) -> Pillar:
    score = fv.coverage_score
    rag = Rag.GREEN if score >= 0.75 else Rag.AMBER if score >= 0.5 else Rag.RED
    c = fv.counts()
    lines = [t("rd.fin.counts", full=c["full"], partial=c["partial"], none=c["none"])]
    if c["none"]:
        none_ids = [s.requirement.id for s in fv.statuses if s.effective.value == "none"]
        actions.append(Action("low", "finma", t("rd.act.finma", n=c["none"],
                                                ids=", ".join(none_ids[:4])), "/finma"))
    return Pillar("finma", rag, f"{score:.0%}", t("fin.score"), lines, "/finma",
                  "FINMA Circ. 2018/3, 2023/1")


def build_readiness(*, report: ValidationReport, quality: QualityScore,
                    analysis: ConcentrationAnalysis, portfolio: Portfolio,
                    plan: RemediationPlan, incidents: IncidentOverview,
                    finma: FinmaView | None = None, lang: str = "en",
                    now: datetime | None = None) -> ReadinessView:
    t = translator(lang)
    actions: list[Action] = []
    pillars = [_register_pillar(t, quality, report, actions),
               _contracts_pillar(t, lang, portfolio, plan, actions),
               _incidents_pillar(t, incidents, lang, actions),
               _concentration_pillar(t, analysis, actions)]
    dora = [p.rag for p in pillars if p.rag is not Rag.GREY]
    overall = min(dora, key=lambda r: r.rank) if dora else Rag.GREY
    if finma is not None:
        pillars.append(_finma_pillar(t, finma, actions))
    order = {"high": 0, "medium": 1, "low": 2}
    actions.sort(key=lambda a: order[a.priority])
    return ReadinessView(pillars, actions, overall, now or datetime.now(UTC),
                         report.reference_date, report.maintainer_name, report, quality,
                         analysis, portfolio, plan, incidents, finma)


def render_readiness_html(view: ReadinessView, *, lang: str = "en", client: str | None = None,
                          prepared_by: str | None = None) -> str:
    """The DORA readiness executive report: self-contained HTML, print/PDF friendly (A4)."""
    t = translator(lang)
    charts = build_charts(view.analysis)
    ctx: dict[str, Any] = {
        "v": view, "t": t, "lang": lang, "client": client or view.entity or "",
        "prepared_by": prepared_by, "version": __version__,
        "fmt": lambda d: format_date(d, lang), "money": money, "pct": pct,
        "charts": {k: Markup(charts[k]) for k in ("groups", "cif")},
        "by_provision": gaps_by_provision(view.portfolio)[:8],
        "humanise": lambda d: humanise(d, lang),
    }
    return environment().get_template("readiness.html.j2").render(**ctx)
