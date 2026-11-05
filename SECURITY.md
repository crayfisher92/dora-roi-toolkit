# Security policy

## Supported versions

| Version | Supported |
|---|---|
| 0.1.x | ✅ security fixes |
| < 0.1 | ❌ |

## Reporting a vulnerability

**Please do not open a public issue for security problems.**

Report vulnerabilities privately through GitHub's
[**Report a vulnerability**](https://github.com/crayfisher92/dora-roi-toolkit/security/advisories/new)
button (Security → Advisories). Include:

* the affected version or commit and how you run it (CLI, library, workbench, Docker);
* a description of the issue and its impact;
* steps to reproduce or a proof of concept – **using synthetic data only**, never real
  client registers.

## What to expect

| Step | Target |
|---|---|
| Acknowledgement | within 3 business days |
| Initial assessment and severity (CVSS) | within 10 business days |
| Fix or mitigation for high/critical issues | within 30 days, coordinated with you |
| Public advisory and credit (if you wish) | after a fixed release is available |

## Scope

In scope: the `dora_roi` package, the `roi` CLI, the workbench web app, the Docker image
and the release workflow in this repository.

Out of scope: deployments exposed to the internet without the authentication and TLS
required by [`docs/SECURITY.md`](docs/SECURITY.md); vulnerabilities in third-party
dependencies without an exploitable path in this project (please report those upstream);
social engineering and physical attacks.

## Safe harbour

We will not pursue legal action for good-faith research that respects this policy, avoids
privacy violations and data destruction, uses only synthetic data, and gives us reasonable
time to fix the issue before disclosure.

The threat model and security controls are documented in
[`docs/SECURITY.md`](docs/SECURITY.md).
