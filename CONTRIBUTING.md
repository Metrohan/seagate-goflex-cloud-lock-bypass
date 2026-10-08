# Contributing

This repository is a documented recovery case study for one Seagate GoFlex Home. Contributions should make the evidence easier to verify without implying that unproven recovery steps work generally.

## Before proposing a change

- Read the root [README](README.md), especially its outcome and limits.
- Keep observations, interpretations, and hypotheses clearly separated. Include device/firmware/host details only when they were actually recorded. Use `unknown` when they were not.
- For commands, state the target, required privileges, expected result, and a safe way to stop or roll back. Distinguish read-only inspection from changes to the NAS, host networking, containers, disks, or firmware.
- Keep credentials, tokens, serial numbers, private keys, raw request bodies, DHCP leases, and identifying logs out of commits and issue reports. Use synthetic test values.
- Do not add firmware or other third-party material unless redistribution rights are clear. The repository MIT License applies only to original repository content as described in [LICENSE](LICENSE).

## Scripts and verification

The `scripts/reg-catcher-test/` harness exercises a synthetic catcher on loopback. It requires Docker, `curl`, and local `cert.pem`/`key.pem` files that are ignored by Git. Its Docker base is Debian 8, which is end-of-life; treat this as a historical compatibility fixture, isolate it, and do not reuse it as a general-purpose or internet-facing service. Follow that directory's README and report the exact command and result.

Other scripts and `scripts/mitm-setup-notes.md` are historical lab artifacts. Do not run them against a NAS or shared network without independently reviewing the target, side effects, and rollback. A synthetic test or successful TLS handshake does not prove registration compatibility or data recovery.

## Pull requests

Use a short English commit/PR title that describes the change. Include: what evidence changed, which claims remain unverified, commands/checks actually run, and any safety or compatibility impact. Do not claim a check passed unless it was executed.
