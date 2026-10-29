# Release, platform and hosting-provider support

**Language / Bahasa / Idioma:** [English](RELEASE_AND_PLATFORM_SUPPORT.md) · [Bahasa Indonesia](RELEASE_AND_PLATFORM_SUPPORT.id.md) · [Español](RELEASE_AND_PLATFORM_SUPPORT.es.md)

This guide distinguishes tested support from possible portability. It does not certify every hosting company or operating-system build.

## Suggested GitHub repository description

> Cross-platform SA-MP/open.mp log triage for Pawn runtime errors, crashes, compiler diagnostics, and admin alerts. Includes CLI, desktop GUI, safe patch preview/apply, and a plugin compatibility catalog.

Suggested topics: `samp`, `openmp`, `pawn`, `log-analysis`, `server-monitoring`, `python`, `developer-tools`.

## Runtime support matrix

| Target | Current support statement |
|---|---|
| Windows desktop | CLI tested on Python 3.10–3.13; GUI requires Tkinter. |
| macOS desktop | CLI tested on Python 3.10–3.13; GUI requires Tkinter. |
| Linux desktop/server | CLI tested on Python 3.10–3.13; GUI requires Tkinter and a display session. Metrics are opt-in and Linux-only. |
| Linux headless server | CLI and monitor are appropriate; GUI cannot run without a desktop display. |
| Android | No native Android app or CI target is shipped. |
| iOS/iPadOS | No native iOS app or CI target is shipped. |
| BSD/other Unix | Not certified by the current CI matrix. |
| SA-MP Pawn bridge | CI compile target is `pawn-lang/compiler v3.10.10` with pinned `samp-stdlib`; live delivery still requires staging verification. |
| open.mp Pawn bridge | CI compile target is `openmultiplayer/compiler v3.10.11` with pinned `omp-stdlib`; live delivery still requires staging verification. |
| Other Pawn compiler versions | Not guaranteed. Compile and stage-test with the exact compiler and includes targeted. |

“Cross-platform” does not mean every OS, CPU architecture, Python release, plugin ABI, or compiler version has been tested. Only the combinations listed by CI are verified at build/test level.

## Hosting providers and DDoS limits

There is no single management API shared by all hosting companies. Provider APIs, account permissions, product tiers, protocols, firewall models, and mitigation capabilities differ.

| Provider/product | Official capability documented | amxtriage status |
|---|---|---|
| Cloudflare Spectrum | Spectrum applications can be created via dashboard or API; UDP support and API fields depend on plan. [Official guide](https://developers.cloudflare.com/spectrum/get-started/). | No automatic API adapter. |
| OVHcloud Game DDoS Protection | OVH documents Game Firewall capabilities and per-IP supported game protocols via API. [Official guide](https://docs.ovhcloud.com/en/guides/bare-metal-cloud/dedicated-servers/firewall-game-ddos). | No automatic API adapter. |
| AWS Shield Advanced | Dedicated API for protections, attacks, and related resources. [Official API operations](https://docs.aws.amazon.com/waf/latest/DDOSAPIReference/API_Operations.html). | No automatic adapter; game endpoint architecture must be confirmed. |
| DigitalOcean Cloud Firewalls | API rules control traffic to/from Droplets; this is not by itself a promise of game-specific volumetric DDoS scrubbing. [Official API](https://docs.digitalocean.com/products/networking/firewalls/reference/api/). | No automatic API adapter. |
| Hetzner Cloud Firewalls | API can manage inbound/outbound firewall rules; firewall rules are not equivalent to universal game DDoS mitigation. [Official API](https://docs.hetzner.cloud/reference/cloud). | No automatic API adapter. |
| Other hosts and reseller panels | API access and protection products vary; some providers offer no public API. | Manual setup until a provider-specific adapter is documented and tested. |

The Pawn bridge is a local diagnostic chat alert, not DDoS mitigation or anti-cheat. Log parsing cannot stop traffic that has saturated an upstream link.

A real provider adapter needs documented endpoints, a protected resource identifier, least-privilege permissions, explicit opt-in, a dry-run, audit records, and staging tests. It must not automatically block addresses or change firewall rules based only on heuristic log signals.

## Recommended GitHub repository settings

Repository description/topics are GitHub metadata, not source files. Suggested settings for a public release:

1. **About:** use the description and topics above; leave Website empty unless an official site exists.
2. **Default branch/ruleset:** keep `main` as default. Require successful CI checks, block force-push and branch deletion, and require pull requests for outside contributors.
3. **Actions:** keep workflow permissions least-privilege. Current CI needs `contents: read`. Before a hardened stable release, pin third-party Actions to reviewed commit SHAs.
4. **Security:** enable Dependabot alerts/security updates, secret scanning and push protection where available. Add `SECURITY.md` and private vulnerability reporting if available.
5. **Release quality:** maintain a changelog, version/tag policy, release notes, wheel and source distribution, bridge artifact checksums, and staging/rollback guidance.
6. **Issues:** request OS, Python version, server type/version, compiler version and a minimal redacted log. Never attach RCON passwords, player credentials or private host data.

The GitHub connection available to this task can update source files and inspect repository metadata, but cannot edit About description/topics or branch rulesets. Apply those settings through GitHub's Settings/About interface.

## Release acceptance checklist

- [ ] CI passes for Python 3.10–3.13 and both named Pawn compiler/header combinations.
- [ ] Bridge tested on staging with the exact server build and permissions.
- [ ] GUI smoke-tested on Windows, macOS and Linux desktop; CLI works on headless Linux.
- [ ] English, Indonesian and Spanish documentation link to each other.
- [ ] Unknown host/compiler/platform combinations remain marked unknown.
- [ ] No production secrets or private logs in fixtures/artifacts.
- [ ] Changelog, security reporting, release notes and rollback guidance are present.
