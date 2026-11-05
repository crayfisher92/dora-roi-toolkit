# 5-minute client demo – DORA RoI Workbench

A scripted walkthrough with the fictional **Alpenrand** banking group, for a first meeting
with a CRO, a head of ICT third-party risk or a compliance team. Timings are approximate; the
figures quoted come from the deterministic sample data (seed 2554).

## Before the meeting (2 minutes, once)

```bash
docker compose up --build -d        # or: pip install -e ".[web]" && roi serve
```

Open <http://127.0.0.1:8000> in a full-screen browser window (1280 px or wider). Light mode
works best on projectors; the **Light** button in the top right forces it. Close other
workspaces by restarting the app (`docker compose restart`) so the demo starts clean.

> Say once at the start: *"Everything you see runs locally on this laptop. The data is a
> fictional bank; nothing leaves the machine and nothing is stored."*

---

## 0:00 – The starting point (30 s)

**Show** the home page.

> "There are three ways in: your RoI workbook, your own contract inventory in whatever format
> procurement gives you, or – for today – a sample: a Swiss group with three EU entities,
> 45 ICT providers and about 120 contracts."

**Click** *Sample with 25 deliberate errors*.

## 0:30 – Where do we stand? (45 s)

**Point at** the header: score **97/100**, *Not ready for submission*, **27 errors**,
**5 warnings**, and the four-step stepper *Import → Fix → Analyse → Export*.

> "97 % of the records are clean – but 27 errors would make the supervisor reject the
> file. The score tells you how far you are; the status tells you whether you can submit."

**Scroll** to *Key messages*: eight provider groups each support five or more critical
functions once subcontracting is counted; five contracts supporting critical functions
expire within a year.

## 1:15 – Fixing, in plain language (75 s)

**Click** *Fix 27 blocking error(s)*, then template **B_02.02** in the left list.

> "Every finding says what is wrong, how to fix it and which DORA or ITS provision it
> supports – no rule codes to look up."

**Find** *FLD-005 Invalid country code* (governing law "UK"). **Click** *Use suggestion: GB*,
then **Save**.

> "The register is re-validated instantly – the error counter in the header just went from
> 27 to 26, without reloading."

Optionally show *FLD-003* (date `31/12/2027` → suggestion `2027-12-31`) and mention that
repeated mistakes can be fixed in bulk.

## 2:30 – One provider, all the facts (45 s)

**Click** *Analyse*, scroll to the **dependency graph**, and click
**Nimbus Cloud Services EMEA Ltd**.

> "This is everything about one provider on one page: if it fails, 13 critical or important
> functions in all three entities are affected; it is hard to substitute, sits in 11 supply
> chains as a subcontractor, and its group is headquartered in a third country. These are
> the questions the board risk committee asks."

Then open its US parent **Nimbus Cloud Inc.** from the *Failure impact* table or the graph:

> "Only one contract is with the US parent directly – but 15 critical functions depend on it,
> 14 of them only through subcontracting chains. That is the concentration you do not see in
> the contract list."

## 3:15 – Concentration and fourth parties (45 s)

**Go back** to *Analyse*; switch *Colour by* to **Region** and press *Update graph*.

> "Direct providers on the left, their subcontractors to the right. The Irish and
> Luxembourg hyperscaler entities roll up to US parents – 24 % of the spend is with groups
> headquartered outside the EEA and Switzerland, although only 8 % is contracted directly
> with third-country entities. That is the hidden concentration DORA Article 29 asks you to
> assess."

**Click** *Open executive summary* to show the CRO report (keep it brief); the *PDF* button next to it produces the same report as an A4 document for the board pack.

## 4:00 – What changed since last year? (30 s)

**Go to** the home page and click *Sample: last year vs this year*.

> "Five new arrangements, one ended – the mainframe outsourcing to *Legacy Mainframe
> Services* – and spend up from about EUR 46.6m to EUR 52.0m. This is your story for the
> annual submission."

## 4:30 – Your data, your language (30 s)

**Click** *Start mapping wizard* → *Use the sample inventory*.

> "This is what we usually receive: a German Excel inventory with a title row,
> `31.12.2025` dates and 'unbefristet'. The wizard recognised 14 of the 15 columns by
> itself and only left the comments column out."

**Click** **DE** in the top right to switch the interface to German.

> "Your business colleagues can work in German; the regulator-facing output stays in the
> official format."

## 5:00 – Close

> "Import, fix, analyse, export – the xBRL-CSV package, the corrected workbook and the CRO
> summary are on the *Export* step. Shall we try it with your own inventory?"

---

### Fallbacks and tips

- **No Docker?** `pip install -e ".[web]" && roi serve` gives the same app.
- **Projector too small?** Use browser zoom (Ctrl/Cmd +); the layout reflows down to phone
  width.
- **Keyboard-only?** Tab from the top: the first stop is *Skip to content*; every action is
  reachable without a mouse.
- **Questions on the xBRL-CSV package:** it is clearly labelled *best effort* – see
  `docs/ASSUMPTIONS.md` (A-XBRL-*) for what must be verified against the EBA taxonomy.
- **Reset** between demos: restart the app; all data is in memory.
