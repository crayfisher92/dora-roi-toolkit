# 10-minute client demo – DORA readiness with the Alpenrand sample

A scripted walkthrough of the full story – **register → contracts → incidents → Switzerland →
CRO report** – with the fictional **Alpenrand** banking group, for a first meeting with a
CRO, a Head of Third-Party Risk or a compliance team. Timings are approximate; the figures
come from the deterministic sample (seed 2554). Only the open major incident is placed
relative to the moment you load the sample, so its reporting countdown is live.

## Before the meeting (2 minutes, once)

```bash
docker compose up --build -d        # or: pip install -e ".[web]" && roi serve
```

Open <http://127.0.0.1:8000> in a full-screen browser window (1280 px or wider). Light mode
works best on projectors; the **Light** button in the top right forces it. Restart the app
(`docker compose restart`) so the demo starts clean – and so the live incident countdown
starts at about 2 h 30 min.

> Say once at the start: *"Everything runs locally on this laptop. The bank is fictional;
> nothing leaves the machine and nothing is stored."*

---

## 0:00 – One bank, four DORA obligations (30 s)

**Show** the home page, **click** *Sample with 25 deliberate errors*.

> "A Swiss group with three EU entities, 45 ICT providers, about 120 contracts. We will look
> at the four things a supervisor asks about: the Register of Information, the ICT
> contracts, incident reporting and concentration – and at what a Swiss parent needs from
> the same data."

**Point at** the *DORA readiness dashboard* box on the overview: four red lights.

## 0:30 – The register: where do we stand? (60 s)

**Point at** the header: score **97/100**, *Not ready for submission*, **27 errors**,
**5 warnings**.

> "97 % of the records are clean, but 27 errors would make the supervisor reject the file."

**Click** *Fix 27 blocking error(s)* → **B_02.02** → *FLD-005 Invalid country code*
(governing law "UK") → *Use suggestion: GB* → **Save**.

> "Plain-language explanation, the DORA provision behind it, and the counter goes from 27
> to 26 without reloading."

## 1:30 – Concentration in 30 seconds (30 s)

**Click** *Analyse*, then **Nimbus Cloud Services EMEA Ltd** in the dependency graph.

> "Eight provider groups each support five or more critical functions once subcontracting is
> counted; two notice deadlines of critical contracts fall within 90 days. If Nimbus EMEA
> fails, 13 critical or important functions in all three entities are affected – that is the
> question the board risk committee asks."

## 2:00 – Contracts: Art. 30 gap analysis (90 s)

**Click** *Art. 30 contracts* in the *DORA programme* row.

> "Every arrangement in the register can be assessed against the 22 key contractual
> provisions of Article 30 – twelve for every ICT service, ten more for services supporting
> critical or important functions. The register decides which apply."

**Point at** the tiles: **120** arrangements, **90** supporting critical functions, **17**
assessed (16 % of the critical ones), **14** with gaps, **35** actions: **18 high**,
15 medium, 2 low. **Scroll** to *Providers, by criticality*: Nimbus EMEA supports 13
critical functions; its two call-offs inherit the master agreement's assessment.

**Click** the filter *Gaps* + *Critical functions only*, then **AR-DE-0026** (Ledgerline):

> "The typical picture of a pre-DORA contract: silent on subcontracting although the
> payment hub is hosted on Nimbus, no audit rights – only an ISAE 3402 report – and no TLPT
> clause."

**Go back**, **click** *HTML* under *Contract remediation plan* (opens in a new tab):

> "This is the deliverable for the client: actions by priority, clause references,
> recommended wording, who owns each action and how far it is – planned, in negotiation,
> agreed – with the agreed target date; Ledgerline's subcontracting clause is already
> overdue. Hyperscaler audit rights sit under *Approved exceptions*, time-boxed until the
> 2027 renewal. Also as PDF and as an Excel workbook to work through with procurement."

## 3:30 – Assess a contract from the document (60 s)

**Open** **AR-DE-0057** (Mobilio digital banking) → **Use the sample contract**.

> "Upload the PDF or Word file and the toolkit pre-assesses it – locally, keyword matching,
> no AI service, nothing leaves the laptop. 17 provisions look present, 4 are not found:
> TLPT, the exit transition period, alternative assurance, cooperation in inspections. The
> audit clause is *possibly partial* – it grants rights to the bank but not to the
> supervisor."

**Point at** the yellow banner *Suggestions – not saved yet* and a matched passage:

> "Every suggestion shows the clause it matched. Nothing is saved until the reviewer has
> checked it – and the audit trail keeps what the tool proposed next to what the reviewer
> decided."

**Click** *Discard suggestions*.

## 4:30 – A major incident, live (90 s)

**Click** *Incidents*.

> "Five incidents. One is open right now: a cloud-region outage at Nimbus taking down core
> banking and payments in Germany and Luxembourg."

**Point at** *Next reporting deadline*: **in ~2 h 29 min**. **Click** the incident:

> "The classification follows the RTS criteria: critical services are affected and five of
> the six other criteria meet their thresholds – 14.6 % of clients, 182 000 clients, 4.5
> hours of downtime, four Member States, media coverage and an estimated EUR 350 000.
> Major."

**Scroll** to *Reporting to the competent authority*:

> "Initial notification four hours after classification – at the latest 24 hours after
> becoming aware; intermediate report 72 hours later; final report a month after that. The
> countdown runs on the page; recording a submission recalculates the next deadlines."

**Scroll** to the questionnaire and point at *Unknown*:

> "In the first hour you won't know everything. Unknown answers are evaluated both ways –
> the result says *undetermined* and lists exactly what you still need to find out."

## 6:00 – The incident nobody reported (45 s)

**Go back** to the log; **point at** the yellow banner *Recurring incidents:
kronos-certificate-rotation*.

> "Two short SEPA instant outages at Kronos in July and November – each below every
> threshold. Same root cause within six months: together they affect 11.6 % of clients and
> 2.75 hours of downtime. Under the RTS that is one major incident – and it was never
> reported."

## 6:45 – Switzerland: one dataset for DORA and FINMA (75 s)

**Click** *Switzerland (FINMA)*.

> "The parent is Swiss. FINMA wants an outsourcing inventory under Circular 2018/3 and
> critical-function and resilience documentation under 2023/1. Instead of a second
> spreadsheet: 24 FINMA requirements mapped to the RoI fields, the Art. 30 checklist and the
> incident log."

**Point at** **56 %** coverage: 5 covered, 17 partly, 2 not covered; then the *Swiss
context*: six Swiss providers with 38 % of the spend.

> "Provider, sub-providers, locations and terms come straight from the register. What FINMA
> needs on top – the responsible unit per outsourcing, scenario tests, FINMA named in the
> audit clause – is listed requirement by requirement."

**Scroll** to *DORA reporting scope of this dataset* (optional, 15 s):

> "And if the Swiss bank's own outsourcings live in the same file, tick it here: it stays in
> the FINMA view and the Excel export, but the xBRL-CSV package for the EU supervisor leaves
> it – and every arrangement only it uses – out. Same on the command line with
> `--exclude-entity`."

(Untick it again before moving on – the sample's entities are all EU entities.)

## 8:00 – One page for the CRO (75 s)

**Click** *DORA readiness*.

> "Everything on one page: register red with 27 errors, contracts red with 18 high-priority
> gaps and only 16 % of critical contracts assessed, incidents red because of the
> unreported recurring series, concentration red. Below: the eight actions that matter,
> each a link to where it is fixed."

**Click** *Open the readiness report* (or *PDF*):

> "The same as a report for the risk committee – A4, as PDF directly or printed from the
> browser, in English or German. Under contracts it says how many of the high-priority
> gaps are actually in negotiation."

## 9:15 – Your language, your data (30 s)

**Click** **DE**.

> "Your business colleagues work in German; the regulator-facing outputs stay in the
> official format."

## 9:45 – Close

> "Register, contracts, incidents, concentration and the Swiss view – from one dataset you
> maintain anyway. Shall we load your inventory next time?"

---

### Fallbacks and tips

- **No Docker?** `pip install -e ".[web]" && roi serve` gives the same app.
- **The same story on the command line** (e.g. for a pre-read):

  ```bash
  roi sample alpenrand.xlsx --assessments assessments.json --incidents incidents.json --contract-document contract.docx
  ```

  ```bash
  roi readiness alpenrand.xlsx --assessments assessments.json --incidents incidents.json -o readiness.html --client "Alpenrand Group"
  ```

  `roi contracts assess`, `roi contracts suggest contract.docx`, `roi incidents summary` and
  `roi finma` produce each part on its own.
- **Countdown already past?** Restart the app – the sample incident is re-created relative to
  now.
- **Keyboard-only?** Tab from the top: the first stop is *Skip to content*.
- **Regulatory questions:** checklist wording, thresholds, deadlines and the FINMA mapping
  are paraphrased and listed as open assumptions in `docs/ASSUMPTIONS.md`.
- **Reset** between demos: restart the app; all data is in memory.
