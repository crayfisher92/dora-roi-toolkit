# Pilot – release candidate 0.2.0-rc.1

A four-week pilot with one client team before 0.2.0 is released. It tests whether the
workbench shortens the preparation of the Register of Information and gives the team a
reliable view of its third-party risk – on the client's infrastructure, signed in with the
client's Entra ID.

## Scope

| In the pilot | Not in the pilot |
|---|---|
| Register: import, fix, validate, xBRL-CSV export, data-quality score, concentration analysis, versions and audit trail | Submission to the competent authority (the pilot's package is checked, not filed) |
| Team use: sign-in, private and team spaces, edit locks | Integration with other GRC tools |
| Programme modules (Art. 30, incidents, FINMA, readiness) – **experimental**, open points in [`MODULE_REVIEW.md`](MODULE_REVIEW.md) | Using module results for decisions without a specialist's review |
| Opt-in GLEIF check, if the client's IT allows outbound HTTPS to `api.gleif.org` | |

## Participants

- Pilot owner at the client (Head of Third-Party Risk or delegate) – decides on data and scope.
- 3–5 users: register maintainers, one contract manager, one ICT risk / incident manager.
- Client IT: hosting, TLS, Entra app registration, backups.
- Information security officer: approves the data classification step (week 2).
- Toolkit maintainers: set-up support, weekly feedback round, fixes as `0.2.0-rc.N`.

## Timeline

| Week | Activities | Done when |
|---|---|---|
| 0 (prep) | Host the team stack ([`TEAM_DEPLOYMENT.md`](TEAM_DEPLOYMENT.md)); run the sign-in test protocol ([`ENTRA_SIGNIN_TEST.md`](ENTRA_SIGNIN_TEST.md)) and `security_selftest.py --team`; encrypted, backed-up projects volume; decide `ROI_GLEIF` | Protocol signed, self-test without FAIL |
| 1 | Kick-off and 10-minute demo ([`DEMO.md`](DEMO.md)); users work with the Alpenrand sample only | Every user has fixed findings, saved a team project and exported a package |
| 2 | **Data gate:** the ISO approves loading the client's register (or an anonymised copy); external penetration test scheduled ([`SECURITY_TESTING.md`](SECURITY_TESTING.md)) | Written approval; real or anonymised register imported |
| 2–3 | Real work: prepare the register for the next reference date, contract and incident modules on a sample of arrangements | Package passes the toolkit's validation; first readiness report |
| 4 | Feedback interviews, SUS questionnaire, wrap-up; decide on 0.2.0 | Exit criteria assessed |

Weekly 30-minute feedback round; issues are filed with the *Pilot feedback* template
(GitHub → New issue), never with real data in screenshots or attachments.

## Data handling

- Synthetic data only until the data gate in week 2.
- Real register data only on the client's host, in the projects volume (encrypted at rest,
  backed up per the client's policy); nothing is sent outside except LEIs if `ROI_GLEIF=1`.
- No real data in issues, chats or e-mails to the maintainers; reproduce problems with the
  sample or describe them.
- At the end: export the projects the client keeps, then delete the volume or hand it over.

## Success criteria

| Measure | Target | How |
|---|---|---|
| Time to a package without blocking errors | at least 40 % less than the last reporting cycle | Pilot owner's estimate of the last cycle vs. time recorded in the pilot |
| Errors found by the toolkit that the previous process missed | reported (no target) | Findings fixed in week 2–3, from the audit trail |
| Usability | SUS score ≥ 70 | Questionnaire in week 4 |
| Blocking defects | none open at the end | Issues labelled `pilot` + `bug` |
| Sign-in and isolation | protocol passed, no finding in the pilot | Week 0 protocol, issues |

## Exit criteria for 0.2.0

1. No open defect labelled `pilot` + `bug` of severity high.
2. External penetration test done; no open high or critical finding.
3. Entra ID sign-in protocol signed by the client.
4. Module review: specialist sign-off on the open items of [`MODULE_REVIEW.md`](MODULE_REVIEW.md),
   or the modules stay labelled *experimental* in 0.2.0.
5. Pilot feedback triaged into the backlog; changelog updated; `0.2.0` tagged per
   [`RELEASING.md`](RELEASING.md).
