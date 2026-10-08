# Seagate GoFlex Home Recovery Manual

> **Project status: field report, recovery incomplete.** This repository documents one authorized GoFlex Home investigation. It is useful as a recovery case study and lab reference; it is not a turnkey recovery image or a promise that old files can be restored. The visible shares did not expose the old user data, and the later physical USB recovery attempt did not restore expected services.

## Start here

| Your goal | Start with | What this repo establishes |
|---|---|---|
| Read files from a working GoFlex Home | [Safe starting procedure](#2-safe-starting-procedure) | A previously observed SMB/FTP access path; old data recovery remains unproven |
| Understand the retired setup dependency | [What happened](#1-what-happened) and [TLS investigation](#4-isolated-cloudtls-investigation) | Observed endpoint shapes and lab experiments, not a replacement cloud service |
| Run the request-catcher unit/integration harness | [Harness README](scripts/reg-catcher-test/README.md) | Synthetic loopback tests only; requires local certificates and an obsolete Debian 8 image |
| Reproduce the firmware recovery | [Firmware recovery notes](#3-firmware-recovery-what-was-learned) | Historical third-party procedure and device-specific observations; no firmware is distributed |

## Tested environment and limits

| Item | Recorded evidence |
|---|---|
| Device | Seagate GoFlex Home; exact hardware revision/label was not recorded in the published evidence |
| Firmware | Community package identified as `hipserv2_seagateplug_2.72_admin.zip`; exact installed build after recovery was not independently recorded |
| Device kernel | Linux 2.6.22.18, observed during the read-only capability review |
| Host/test environment | Debian Jessie/OpenSSL 1.0.1 was used for legacy TLS investigation; the isolated catcher harness is Docker-based |
| Verified outcomes | Basic FTP/SMB reachability after firmware recovery; synthetic catcher tests passed in the recorded run |
| Not verified | Restoration of old user files, successful completion of account registration, or recovery of expected services after the later USB image attempt |

Do not infer compatibility with another GoFlex hardware revision, firmware package, or disk layout from this single case. Unknown values are intentionally marked unknown instead of guessed.

This repository records a cautious recovery effort for a Seagate GoFlex Home running Axentra HipServ. Seagate discontinued GoFlex Home remote access effective **December 31, 2018**. Seagate said local-network features and on-device data should remain, but a later reset/setup flow may still depend on the retired service. This effort addressed that specific locked setup state; it does not imply that every GoFlex Home requires a firmware reflash.

The work was performed on an authorized device over a directly connected, isolated lab network. This manual distinguishes **what was observed**, **what worked**, and **what remains unproven**. It is a record of one device with incomplete hardware/firmware identification, not a universal recipe.

> **Current documented outcome (2026-10-02): recovery is incomplete.** FTP/SMB access was restored, but the old user data did not appear in the visible shares. A DLNA inventory was collected. A later USB recovery image passed offline checks, but after the physical recovery attempt the device did not return its expected services. Successful NAND recovery, SSH access, and access to the old data were not established. Use the verified SMB path while deciding whether to continue.

## 1. What happened

### The original problem

The NAS could no longer complete its normal cloud-assisted setup because Seagate had retired the service. The immediate question was whether the disk and files were still intact, or whether the device had simply lost the account/share view that exposed them.

The first useful clue was a mismatch: FTP and SMB became reachable after firmware recovery, while the visible user shares looked empty. The disk reported roughly **1.46 TB in use**. That number is evidence that storage was occupied; it does not identify the files, prove that the old data is intact, or mean those files can be copied through the current account.

### Restoring basic file access

The firmware-recovery USB initially did not boot as expected while the internal SATA disk remained installed. The bootloader was treating the internal disk as `/dev/sda`, the same device name expected for the USB recovery drive. Removing the SATA disk during the recovery boot resolved that device-selection conflict. The community firmware procedure then restored ordinary network and file-sharing access and created a local administrator account.

Afterward, SMB and FTP were reachable. Because this firmware uses legacy SMB, the workstation needed SMB1/NT1 compatibility for the isolated link. The `Personal` share was observed to be empty; timeouts on other shares were inconclusive. The original files may still be on disk, but access through the visible shares was not recovered.

### Finding the cloud dependency

The first hypothesis was that setup depended on `reg.seagateshare.com`. A controlled DHCP/DNS and traffic-observation setup showed that the observed boot path used different endpoints, including:

- `GET /cpestatus` on `cpestatus.seagateshare.com`
- `POST /rest/1.0/status/hipserv` on `www.seagateshare.com` with the unusual `txt/xml` content type
- an update-check request under `/downloads/updates/autocheck.php`

Only endpoint shapes and redacted metadata belong in this repository. Device serials, registration passwords/tokens, raw request bodies, and private keys must stay out of Git and logs.

### Making the old TLS client observable

The NAS speaks an obsolete TLS dialect. A modern TLS terminator was not initially compatible with its SSLv2-compatible ClientHello, so a Debian Jessie/OpenSSL 1.0.1 environment was used for bounded protocol investigation. One detached `openssl s_server` attempt closed the connection before accepting the TLS handshake: the old process read EOF from its closed standard input and shut down. Keeping standard input open with a pipe fixed that specific test-runtime failure.

The static `s_server -HTTP` response was useful for `/cpestatus`, but it could not safely model the unknown registration API. A separate Python catcher behind `stunnel` was built to observe request method, path, headers, and body shape while redacting sensitive fields. Its canned XML response is explicitly **synthetic**; it is not represented as the real Seagate/Axentra protocol. The isolated catcher tests passed, and a later boot produced real endpoint observations. Those observations did not prove that local account creation or registration could be completed.

### Data recovery and management-UI decision

A read-only DLNA `ContentDirectory` inventory was collected and accepted as a bounded result; it did not change the NAS flash or disk. The later USB `initrd` attempt used an RSA key format compatible with the device's old OpenSSH, and the image was checked offline for filesystem consistency, U-Boot CRC, payload identity, and checksum before being placed on the USB drive. The physical attempt did not bring the expected services back, so the result is **unverified**, not a successful recovery.

A proposed embedded management UI was stopped at a read-only capability gate. The NAS has an expired self-issued certificate and obsolete TLS, independent authentication was not established, reboot-safe application storage ordering was unknown, and no narrow privilege boundary for account/share changes was proven. A bounded ARMv5 proxy investigation also stopped because the device's Linux 2.6.22.18 kernel falls below the supported kernel baseline of current Go releases. The safe direction recorded in the project is ordinary SMB access and a maintained LAN-side TLS-capable host before reconsidering a UI.

## 2. Safe starting procedure

### Scope and safety

1. Work only on a device you own or are authorized to administer.
2. Connect it to a dedicated Ethernet interface on a workstation. Keep the NAS isolated from the internet and shared LAN during legacy protocol work.
3. Do not reset, format, repartition, or reflash a disk that may contain the only copy of important files.
4. Keep passwords and tokens out of command history, issue reports, screenshots, shell transcripts, and Git. Use interactive prompts or local secret files with restrictive permissions.
5. Treat old SMB1, the firmware's default/local account, and its HTTPS service as unsafe outside the isolated link.
6. Before any firmware or host-network change, record the current interface/routes and prepare a rollback. Stop if the board, firmware package, or target disk is uncertain.

### Inspect the direct link

Identify the dedicated interface and route before scanning. Substitute your own values:

```sh
ip -br address
ip route get "$NAS_IP"
ip neigh show "$NAS_IP"
nmap -Pn -p 21,22,80,443,139,445 "$NAS_IP"
```

These checks were used to separate “NAS is offline” from “traffic is going over the wrong interface.” A ping alone is not enough to establish the route or service state.

### Try ordinary file access first

Use an interactive password prompt. Enable NT1 only for the isolated legacy connection:

```sh
smbclient -L "//$NAS_IP" -U "$NAS_LOGIN" --option='client min protocol=NT1'
smbclient "//$NAS_IP/Personal" -U "$NAS_LOGIN" --option='client min protocol=NT1'
```

At the `smb: \>` prompt, use `ls` to inspect and `get <remote-file>` to copy a file. Copy recovered data to a separate disk and verify it before attempting firmware work. An empty share or a timeout on one share does not establish that the internal disk is empty.

FTP was also observed working after the firmware recovery. Prefer ordinary SMB/FTP copy access over modifying the NAS while the goal is data recovery.

## 3. Firmware recovery: what was learned

Reflash is a last resort for a device still blocked by the retired setup service. It changes the NAS firmware and can make the unit unbootable. Seagate's shutdown guidance says not to factory-reset or upgrade/downgrade firmware after remote access has ended. The procedure below records an unsupported community recovery used on this device; it is not Seagate-approved. The package was a third-party archive named `hipserv2_seagateplug_2.72_admin.zip`; it is not included here, and its provenance and redistribution rights are uncertain.

The key device-specific lesson was the disk/USB device-name collision. The internal SATA disk was removed for the recovery boot so the bootloader could find the USB image. Do not copy this step blindly: verify the exact board, recovery procedure, package contents, and disk backup situation for your device first.

The later custom USB image was prepared without putting the private RSA key into the archive. Offline checks included `e2fsck -fn`, U-Boot CRC validation, size/content comparison for unchanged components, and SHA-256 verification. These checks establish properties of the image; they do not prove that the device accepted it or booted successfully. After the physical attempt, expected services did not return.

Firmware references and original recovery details are listed in [References](#8-references). No firmware image or private key is distributed by this repository.

## 4. Isolated cloud/TLS investigation

The MITM work was a protocol-observation experiment on an isolated link, not a supported way to restore Seagate's cloud service. The detailed historical host/container notes are in [`scripts/mitm-setup-notes.md`](scripts/mitm-setup-notes.md). Read them as an audit trail; they contain host-network and container commands that must not be run without reviewing the exact target, current state, rollback, and authorization.

The experiment used:

1. A dedicated Ethernet link with DHCP/DNS supplied by `dnsmasq`.
2. A local name/traffic path to observe requests that the device otherwise sent to retired service hostnames.
3. A legacy TLS environment for compatibility testing.
4. A dynamically routed HTTP catcher that logged redacted request metadata and returned a clearly synthetic response for observation.

The first expected registration hostname was not contacted in the observed boot. Real requests exposed the `/rest/1.0/status/hipserv` endpoint, the `txt/xml` content type, `/cpestatus`, and an update-check endpoint. The catcher was updated to treat `txt/xml` as text and to redact XML-element secrets as well as query, form, JSON, and header values. Capturing a request or completing TLS is not proof that the device accepted an account, created a local login, or exposed old data.

Do not expose the NAS's legacy web interface on a shared LAN. The 2026-10-02 capability review was **NO-GO** for an embedded UI; use a maintained, isolated host for any future modern management surface.

## 5. Scripts and repository files

The repository contains two different kinds of tooling: historical lab helpers and a synthetic catcher test harness. **Only the catcher harness has a self-contained test entry point.** The other scripts are evidence from the original investigation and should not be treated as turnkey setup commands. Review [CONTRIBUTING.md](CONTRIBUTING.md) before proposing changes or sharing logs.

| Path | Purpose | Boundary |
|---|---|---|
| [`scripts/dnsmasq_goflex.conf.example`](scripts/dnsmasq_goflex.conf.example) | Starting point for the isolated DHCP/DNS test network | Example only; inspect interface, subnet, and routing before use |
| [`scripts/catcher.py`](scripts/catcher.py) | Earlier HTTP request catcher used during endpoint observation | Historical utility; no standalone public run procedure is claimed. Review bind address, logging, and redaction before any use |
| [`scripts/mitm-setup-notes.md`](scripts/mitm-setup-notes.md) | Detailed chronology and commands for the legacy TLS/DNS/container investigation | Audit notes, not blanket permission to change the host or NAS |
| [`scripts/reg-catcher-test/`](scripts/reg-catcher-test/) | Isolated Jessie/OpenSSL + `stunnel` + Python catcher test harness | Uses synthetic requests and loopback-only ports; it does not test the real NAS or prove API compatibility |
| [`docs/superpowers/specs/2026-09-25-reg-catcher-test-design.md`](docs/superpowers/specs/2026-09-25-reg-catcher-test-design.md) | Design and security boundaries for the catcher test | Design record |
| [`docs/superpowers/plans/2026-09-25-reg-catcher-test.md`](docs/superpowers/plans/2026-09-25-reg-catcher-test.md) | Implementation and verification plan for the isolated catcher | Historical execution record |
| [`docs/superpowers/evidence/2026-10-02-goflex-ui-capability-gate.md`](docs/superpowers/evidence/2026-10-02-goflex-ui-capability-gate.md) | Evidence and decision that stopped the embedded management UI | Read-only findings; no mutation endpoint was deployed |

### Running only the isolated catcher checks

The harness requires Docker, `curl`, and local `cert.pem`/`key.pem` files that are ignored by Git. From the repository root:

```sh
sh scripts/reg-catcher-test/build-run-test.sh
```

This builds a test-only image, publishes ports on `127.0.0.1`, sends synthetic HTTP/HTTPS requests, and checks the redaction behavior. It does not change firewall rules, start a production-named container, reboot the NAS, or validate the real device's registration protocol. See the harness [README](scripts/reg-catcher-test/README.md) before use.

## 6. What is and is not proven

| Claim | Status |
|---|---|
| The retired cloud service is a blocker for the original setup flow | Observed/documented |
| Firmware recovery restored basic FTP/SMB reachability | Previously observed on this device |
| The visible `Personal` share contained the old user files | Not observed |
| The disk's used-space figure means files are recoverable | Not proven |
| The isolated TLS catcher can accept synthetic HTTP/HTTPS tests and redact test secrets | Verified in the recorded test run |
| A synthetic XML response matches the real Seagate/Axentra registration schema | Not proven |
| The local account-registration sequence is fully emulated | Not proven |
| The later USB recovery attempt restored the device's services | Not proven |
| The embedded management UI has safe authentication, TLS, storage ordering, and privilege boundaries | No-go; requirements were not established |

## 7. Handling and contribution rules

- Never commit `cert.pem`, `key.pem`, private keys, credentials, tokens, raw NAS request bodies, local DHCP leases, or logs containing device data.
- Keep test values visibly synthetic. Review logs before sharing them; redact query, form, JSON, header, XML, and binary/body data as appropriate.
- Do not copy commands from the historical MITM notes into a live shell without checking each target and rollback.
- Do not claim recovery success based on LEDs, a TLS handshake, a synthetic HTTP `200`, a DLNA listing, or a disk-usage value. Verify login, a representative file copy, checksums, and behavior after a normal reboot.
- Firmware files are omitted because their source and redistribution rights are uncertain.
- The repository uses the [MIT License](LICENSE) for its original documentation and scripts; third-party firmware, tools, and referenced material remain under their own terms.
- See [CONTRIBUTING.md](CONTRIBUTING.md) for evidence, safety, and documentation expectations when proposing changes.

## 8. References

### Device and recovery background

- [Seagate: GoFlex Home LED functionality](https://www.seagate.com/support/kb/goflex-home-led-functionality-3205en/)
- [Seagate: GoFlex Home remote-access shutdown](https://www.seagate.com/support/kb/goflex-home-remote-access-shutdown-007857en/) — official 2018 notice
- [Seagate: what to know after remote access was discontinued](https://www.seagate.com/in/en/support/kb/what-to-know-about-goflex-home-and-the-discontinuation-of-remote-access-007867en/) — local access and factory-reset warnings
- [Community GoFlex Home firmware reflash procedure](http://goflexhome.blogspot.com/2019/01/firmware-reflash-without-seagateshare.html) — third-party source; verify the archive yourself
- [BeyondLogic archived recovery boot log](https://web.archive.org/web/2020id_/https://wiki.beyondlogic.org/index.php/Seagate_FreeAgent_GoFlex_Home_Firmare_Recovery) — documents the USB recovery behavior
- [FreeBSD forum discussion quoting the GoFlex recovery procedure](https://forums.freebsd.org/threads/sending-a-file-via-serial-port.66335/) — corroborates removing the SATA disk when it is mistaken for the USB device
- [OpenStora project](https://github.com/Dees7/openstora) — reference during the local sign-in and firmware investigation; not proof that its mechanisms apply to GoFlex

### Protocol and platform constraints

- [Debian archive](http://archive.debian.org/debian) — historical package source examined for the isolated Jessie/OpenSSL compatibility environment
- [Go minimum requirements](https://go.dev/wiki/MinimumRequirements), [Go Linux support](https://go.dev/wiki/Linux), and [Go ARM support](https://go.dev/wiki/GoArm) — used in the bounded ARMv5 proxy feasibility review
- [`scripts/mitm-setup-notes.md`](scripts/mitm-setup-notes.md), the catcher [design](docs/superpowers/specs/2026-09-25-reg-catcher-test-design.md), and the [capability-gate evidence](docs/superpowers/evidence/2026-10-02-goflex-ui-capability-gate.md) record project-specific observations and limitations.

Firmware is not included in this repository. This manual is for authorized recovery and reuse of your own device.
