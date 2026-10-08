# GoFlex Management UI Capability Gate

Date: 2026-10-02
Result: NO-GO - stop before implementation

Scope: read-only SSH inspection of GoFlex Home at 192.168.50.89. No device files, accounts, shares, services, or settings were changed. No management helper or account/share operation was executed. No credential, password hash, private key, or raw sensitive config was recorded.

## Evidence

| Gate | Observation | Result |
|---|---|---|
| HTTPS and Apache | Apache 2.2.3 has a _default_:443 vhost; SSL and CGI modules are loaded; httpd -t reports Syntax OK. | Present |
| TLS certificate | Configured public certificate is self-issued for localdomain; validity ended 2018-10-07. | Fail |
| Existing authentication | Existing Basic Auth paths use the device registration SQLite database (users.LoginID / users.Crypt). An independent UI credential store/auth boundary is not established. | Unknown / fail gate |
| CGI identity | Apache runs as UID/GID apache (48); CGI and SSL modules are loaded. Existing routes include /admin, /support, and /update. | Present, insufficient |
| Disk and app storage | /dev/sda is mounted at /mnt/eSata as UFS with rw; 1,364,795,172 KiB is available. Root UBI has 57,688 KiB available. The boot hook scans USB devices, but existing evidence does not prove the proposed app path is mounted before Apache after every normal reboot. | Current mount present; persistence unknown |
| SMART | smartctl -H /dev/sda reports SMART Health Status: OK. | Pass |
| Sudo boundary | Installed sudo does not support sudo -l -U. The readable sudoers policy grants commands to root and %admins, not Apache; Apache groups do not include admins. | No sudo allowlist for Apache |
| Privileged helper | /usr/sbin/oe-admin-helper is root-owned, setuid, group www; Apache belongs to www. Static strings show fixed family-share operations and also a generic set-config <file> <key> <value> <delim> interface. No safe narrow interface for proposed account/share operations was proven. The helper was not invoked. | Fail gate |
| Existing account path | Helper references and existing admin Perl code exist, but a safe callable contract for UI mutations was not established. | Unknown |

## Decision

Do not implement mutation endpoints or deploy an interface. Required gates are not met: TLS is expired, independent authentication is unproven, reboot-safe app storage is unproven, and no allowlisted privilege path for user/share operations is established.

The approved plan requires stopping when any gate fails or remains unknown. The user has now selected prerequisite remediation. That authorizes read-only investigation and planning only; each live-device change still needs its own approval after showing the exact command, backup, expected effect, and rollback. Replacing the certificate, changing authentication, modifying Apache, invoking the helper, or changing accounts/shares remains outside this read-only gate.

## Commands and limits

Read-only checks included Apache vhost/module/config validation, public certificate metadata, auth directive paths, mount/space state, SMART health, sudoers text, helper file metadata/static strings, and startup mount-hook source. Certificate client-trust chain, normal-reboot persistence, helper implementation/complete call contract, and any mutation operation were not tested.

The user selected prerequisite remediation after this initial gate result; follow-up evidence and the current next action are recorded below.

## Follow-up compatibility findings

A modern client probe (curl 8.22.0 / OpenSSL 3.6.5) could not establish the current HTTPS endpoint. A TLS 1.2-only handshake was rejected as unsupported. A TLS 1.0 handshake succeeded only after enabling legacy renegotiation on the diagnostic client; the negotiated connection used a 1024-bit DHE key and reported MD5-SHA1. This confirms that renewing only the certificate cannot make the existing Apache/OpenSSL 0.9.8b endpoint compatible with current clients.

The GoFlex boot runlevel links start Apache at S85 and oe-bootfinish at S99. The latter calls the USB/SATA mount-at-boot hook. Therefore the proposed app route must not assume that /mnt/eSata exists when Apache starts; no prior boot log was present to prove a stronger ordering guarantee.

## Consequence and revised prerequisite direction

There is no safe certificate-only fix. A modern TLS termination layer would require either a separate maintained LAN host or widening the device scope to add and maintain a modern reverse-proxy runtime on ARMv5. The latter conflicts with the approved plan constraint against installing a new runtime and has not been compatibility-tested. The Archer AX12 may offer VPN-server features depending on hardware revision and firmware, but a router VPN does not itself provide modern HTTPS termination on the NAS; the exact device and LAN-side isolation behavior remain unverified. The development host is x86_64 and no ARM cross-compiler was found in PATH, so an on-device proxy feasibility spike would first need an approved build/toolchain plan.

Do not expose the GoFlex management UI on shared LAN HTTP or legacy HTTPS. Account/share mutation remains separately blocked until a narrow privilege helper contract is proven or designed and reviewed. The user chose to test prerequisite feasibility first; the bounded result and resulting SMB fallback are recorded below.

## Bounded ARMv5 proxy feasibility spike

The host compiler is Go 1.27.1. Official Go support documentation lists GOARM=5 for ARMv5, but current Go releases require Linux 3.2 or later; the Go Linux support table lists 2.6.23 as the oldest kernel supported by the final Go 1.18 release. The GoFlex kernel is 2.6.22.18, below both supported baselines:
- https://go.dev/wiki/MinimumRequirements
- https://go.dev/wiki/Linux
- https://go.dev/wiki/GoArm

Decision: stop the ARMv5 Go proxy spike before downloading toolchains or building a binary. A custom C/nginx/OpenSSL cross-build may be theoretically possible, but no ARM cross-compiler is installed and it would become a bespoke runtime on an unsupported kernel. That exceeds the bounded feasibility scope and creates an ongoing patching burden. The user authorized stopping here and using standard SMB until a maintained server is available.

Final next action: continue ordinary SMB access; revisit the management UI only after a maintained TLS-capable host is available.
