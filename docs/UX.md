# UX design: DORA RoI Toolkit web app

This document was written **before** the web redesign was built. It fixes who the app is
for, what they need to get done, and the screen flow that serves those jobs. Engineering
choices that follow from it are in [DECISIONS.md](DECISIONS.md) (D-024 onwards).

## Personas

### 1. Lena – external GRC consultant

| | |
|---|---|
| **Role** | Senior manager in a Big-4 / boutique GRC practice; runs 4–6 DORA mandates a year for mid-size banks, insurers and asset managers in DACH and Luxembourg. |
| **Context** | Gets the client's "contract inventory" as an Excel file exported from a procurement or contract-management tool, with the client's own column names (German or English), merged cells, `31.12.2025`-style dates and country names instead of ISO codes. Has 2–3 weeks to turn it into a fileable register and a board-ready concentration analysis. |
| **Goals** | Convert messy inventories into the RoI templates quickly and repeatably; find and fix data issues *with* the client in a workshop; produce a credible executive summary for the CRO; compare this year's register with last year's. |
| **Frustrations** | Spreadsheet ping-pong with the client; validation errors that cite technical rule IDs without saying what to do; tools that need IT installation at the client; no way to show the client "what changed". |
| **Success** | "In the second workshop we fixed the 40 open issues live on the screen and I sent the CRO pack the same afternoon." |
| **Devices** | Laptop, often connected to a client projector (1280 px wide, light mode, sometimes high-contrast settings). Runs the app locally via Docker. |

### 2. Thomas – in-house third-party risk manager

| | |
|---|---|
| **Role** | Head of ICT third-party risk at a regional bank (second line); owns the register year-round, reports to the CRO and the board risk committee. |
| **Context** | The register lives in an Excel workbook maintained with procurement and the business. Before the annual submission (and whenever the supervisor asks) he must make sure it is complete and consistent, and he answers ad-hoc questions: "which critical functions depend on Nimbus?", "what happens if this provider fails?". |
| **Goals** | Know at a glance whether the register is submittable; drill from a risk metric to the provider and its contracts; understand subcontracting chains; explain changes since the last submission. |
| **Frustrations** | No single view of a provider across templates; fourth parties are invisible; German-speaking colleagues in the business prefer a German interface; accessibility requirements of the bank's IT policy (WCAG 2.2 AA). |
| **Success** | "Before the submission I see 'Ready' and a quality score of 100, and when the CRO asks about Nimbus I open its page and show the five critical functions and the chain behind it." |
| **Devices** | Desktop with two monitors; dark mode; uses keyboard heavily; occasionally checks figures on a tablet. |

## Key jobs to be done

| # | Job | Persona | Feature |
|---|---|---|---|
| J1 | *When I receive a client's own inventory, I want to map their columns to RoI fields, so I don't have to retype anything.* | Lena | Column-mapping import wizard with auto-suggestions and preview |
| J2 | *When I open a register, I want to know immediately whether it can be submitted and how far away it is.* | both | Progress stepper + data-quality score + "Ready / not ready" status |
| J3 | *When there are validation errors, I want to understand them in plain language and fix them where I see them.* | both | Fix screen: findings grouped by template and severity, explanation, regulation, editable cell, instant re-validation |
| J4 | *When the same mistake appears 30 times ("UK" instead of "GB"), I want to fix it once.* | Lena | Bulk fix with suggested replacement |
| J5 | *When someone asks about a provider, I want everything about it on one page.* | Thomas | Provider detail: contracts, functions, chain, risk flags, open issues |
| J6 | *When I assess concentration, I want to see the hidden fourth parties.* | Thomas | Interactive dependency graph coloured by criticality or region |
| J7 | *When I prepare the annual submission, I want to explain what changed since last year.* | both | Register diff (added / removed / changed providers and contracts) |
| J8 | *When I'm done, I want the files the supervisor and the CRO need.* | both | Export step: xBRL-CSV (best effort), corrected Excel, reports |
| J9 | *I want to work in German or English, with the keyboard, in light or dark mode.* | both | i18n EN/DE, WCAG 2.2 AA, theme toggle |

## Information architecture and screen flow

```
                        ┌────────────────────────── Home ───────────────────────────┐
                        │ Upload RoI workbook · Map own inventory · Load sample     │
                        │ Recent workspaces · Compare two registers                 │
                        └──────────────┬──────────────────────────┬─────────────────┘
                                       │                          │
                     RoI workbook / CSV / package         Own inventory (.xlsx/.csv)
                                       │                          ▼
                                       │          Mapping wizard: 1 Upload → 2 Map columns
                                       │          (auto-suggested) → 3 Entity details →
                                       │          4 Preview → Import
                                       ▼                          │
 ┌──────────── Workspace (stepper: ① Import ✓  ② Fix  ③ Analyse  ④ Export) ──────────────┐
 │ Overview  – quality score, status, counts, next best action                          │
 │ ② Fix     – findings by template ▸ severity ▸ rule; plain-language help, regulation;  │
 │             edit cell → re-validate; bulk fix; filters                                │
 │ Register  – one tab per template; search, filter "with issues"; edit cells            │
 │   └─ Provider page – profile, risk flags, contracts, functions, chain, issues         │
 │ ③ Analyse – concentration dashboard; dependency graph (colour by criticality/region)  │
 │ ④ Export  – xBRL-CSV (best effort), Excel with fixes, CSV, validation & CRO reports   │
 │ Compare   – diff against another workspace or an uploaded previous version            │
 └──────────────────────────────────────────────────────────────────────────────────────┘
```

### Screen notes

1. **Home.** Three clear entry points, one per starting situation. The sample is a first-class
   option so a demo never depends on client data.
2. **Mapping wizard.** One decision per screen. Columns are shown with three sample values; the
   suggested target is pre-selected with a confidence hint ("matched header 'Vertragsnummer'").
   Values are normalised on import (country names → ISO codes, `31.12.2025` → ISO dates,
   `ja/nein` → booleans, service descriptions → ICT service types) and the preview shows the
   normalised value next to the original. Unmapped columns are allowed.
3. **Workspace overview.** The stepper is always visible; the score and status are the first
   thing read. One *next best action* button ("Fix 27 blocking issues").
4. **Fix.** Grouped and collapsible: *template → severity → rule*. Each rule group shows the
   plain-language explanation and the regulation; each finding row shows the record, the
   current value and an inline input with the suggested value pre-filled where one exists.
   Saving re-validates and updates the counts in place (announced via an ARIA live region).
   A bulk action appears when the same value is wrong in several rows.
5. **Register.** Dense, searchable tables; issues are marked per row; cells are editable.
6. **Provider page.** Header with risk flags (supports N critical functions, hard to substitute,
   no exit plan, third-country group, expiring, not audited); tables for contracts and
   functions; the provider's own chain as a small graph; open findings.
7. **Analyse.** The concentration dashboard from the CRO report plus the dependency graph.
   The graph has a legend, a "colour by" switch, a "critical chains only" filter, keyboard-
   focusable nodes linking to provider pages and a table alternative.
8. **Export.** Each output explains what it is for and its caveats (xBRL-CSV best effort).
9. **Compare.** Summary tiles (added / removed / changed) per object type, then detail tables
   with old → new values.

## Interaction and accessibility principles

- **Progressive enhancement.** Every action is a normal form or link that works without
  JavaScript; JavaScript adds in-place updates, filtering and graph interactivity.
- **WCAG 2.2 AA.** Semantic landmarks, skip link, visible focus (2 px), labels on every input,
  ≥ 24 × 24 px targets (2.5.8), 4.5:1 text contrast in both themes, status never by colour alone
  (icon + text), live regions for re-validation, `lang` set per locale, tables with headers,
  no keyboard traps, reflow at 320 px (tables scroll inside their container).
- **Plain language first, regulation second.** Every finding answers *what is wrong*, *how to
  fix it* and *why it matters*, then cites DORA / ITS.
- **Never lose data.** Invalid values stay visible and editable; every edit creates a new
  version, and versions can be compared.
- **Calm visual language.** One accent colour, status colours only for severity, data colours
  only in charts (validated for colour-vision deficiencies in both themes).
