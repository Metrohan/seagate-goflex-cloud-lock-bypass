# Seagate GoFlex Home Recovery How-To

This guide documents a recovery path for a Seagate GoFlex Home running Axentra HipServ after Seagate discontinued the `seagateshare.com` service. It is based on work on an authorized device connected to an isolated lab network. Hardware, firmware, and current device state can differ; adapt and verify every step before use.

## Current project status

**Last documented capability review: 2026-10-02.** A read-only assessment of an on-device management UI ended **NO-GO**. The device's HTTPS stack is obsolete, independent authentication was not established, app storage persistence across reboot was unproven, and no narrow privilege boundary for account/share changes was verified. The review changed no files, accounts, shares, services, or settings on the NAS. Use ordinary SMB access for now; do not expose the legacy web UI as a management interface.

Earlier observations confirmed FTP/SMB access after recovery, but visible shares appeared empty even though the disk showed about 1.46 TB in use. That does not prove the old data is gone or accessible. The device's present live state has not been rechecked by this repository.

## Safety and scope

- Work only on a device and network you own or are authorized to administer.
- Use a direct, isolated Ethernet link. Do not attach this legacy device to a shared or internet-facing network during recovery.
- Do not factory-reset, repartition, format, or reflash a disk that may contain the only copy of important data.
- Firmware reflash changes the NAS firmware and can leave the device unbootable. Verify the exact board and firmware package, preserve a separate data backup where possible, and stop if the package or recovery mode is uncertain.
- The community firmware referenced below is third-party and is not included in this repository. Verify its provenance and integrity yourself before use.
- SMB1 and the device's default credentials are unsafe on untrusted networks. Keep any legacy protocol use isolated and never publish passwords, tokens, private keys, or raw device configuration.
- Do not treat an LED, a successful TLS handshake, a synthetic HTTP response, or a large disk-usage number as proof that old files are recoverable.

## 1. Prepare an isolated connection

Connect the NAS directly to a dedicated Ethernet interface on a Linux workstation. Disconnect that interface from NetworkManager or other network management only if you understand how to restore it afterward. Choose an address range that does not overlap another network, then identify the NAS address from DHCP leases or the device's network settings.

Inspect only the isolated link. For example:

```sh
nmap -Pn -p 21,22,80,443,139,445 "$NAS_IP"
```

`$NAS_IP` is a placeholder for the address assigned to your device. Do not scan networks you do not own or administer.

## 2. Check SMB shares and copy accessible files

Install or use a Samba client on the workstation. Older GoFlex firmware may require SMB1; enable that compatibility only for this isolated connection. The client prompts for the password, so it does not need to appear in shell history.

List the shares:

```sh
smbclient -L "//$NAS_IP" -U "$NAS_LOGIN" --option='client min protocol=NT1'
```

Connect to a share and inspect its contents:

```sh
smbclient "//$NAS_IP/Personal" -U "$NAS_LOGIN" --option='client min protocol=NT1'
```

At the `smb: \>` prompt, use `ls` to list entries and `get <remote-file>` to copy one file to the workstation's current directory. Repeat for each available share. Store recovered files on a separate disk and verify the copies before changing firmware or storage.

A share that lists as empty does not establish that the physical disk is empty. Previous checks found about 1.46 TB in use while several visible shares looked empty. Avoid formatting or repartitioning the disk while data recovery remains the goal.

## 3. Reflash only if the device is still locked

This procedure was used to restore network and file-share access. Skip it if your device is already accessible or if you cannot accept the firmware risk.

The cited community package is `hipserv2_seagateplug_2.72_admin.zip`; it is third-party firmware, is not distributed here, and its licensing/provenance is uncertain. The original procedure is described by [GoFlex Home blog](http://goflexhome.blogspot.com/2019/01/firmware-reflash-without-seagateshare.html). The critical recovery detail was documented in a [BeyondLogic archived boot log](https://web.archive.org/web/2020id_/https://wiki.beyondlogic.org/index.php/Seagate_FreeAgent_GoFlex_Home_Firmare_Recovery).

1. Confirm the exact GoFlex board and package compatibility. Verify the downloaded archive and the firmware components' formats/checksums using trusted tools and instructions.
2. Power the NAS off and remove the internal SATA disk from the dock. The recovery boot process may otherwise mistake the disk for the USB drive (`/dev/sda`) and fail to find the recovery image. Removing the disk also keeps it out of the firmware-writing path.
3. Prepare the FAT32 recovery USB exactly as required by the package's source instructions.
4. Insert the USB drive. Hold the reset pin while powering on to enter recovery mode.
5. Allow several minutes for both bootloader and firmware stages to finish. Do not interrupt power while writing is in progress.
6. Power off, reinstall the SATA disk, and boot normally. Confirm network connectivity and SMB access; an LED alone is not sufficient verification.

The package used in the documented recovery created an `admin` account. Treat any bundled/default credential as temporary, use it only over the isolated link, and change it through a supported, verified method if available. Do not reuse it elsewhere.

## 4. Do not rely on the legacy web interface

The original web interface depends on old Flash-era components and redirects through the discontinued cloud service. A read-only inspection on 2026-10-02 found Apache 2.2.3 and OpenSSL 0.9.8b-era TLS, an expired self-issued certificate, and compatibility failures with modern clients. A modern client could negotiate only after legacy TLS options and received a weak 1024-bit DHE key with MD5-SHA1.

The proposed embedded management UI was stopped before implementation. Authentication independence, reboot-safe storage ordering, and a safe allowlisted account/share operation path were not proven. Do not put a management UI on shared LAN HTTP or the NAS's legacy HTTPS endpoint. The bounded ARMv5 proxy feasibility investigation also stopped; the supported kernel baseline was newer than this device's Linux 2.6.22.18 kernel.

## Repository contents

- `scripts/catcher.py` — HTTP request catcher used in the lab investigation.
- `scripts/dnsmasq_goflex.conf.example` — example DHCP/DNS configuration; adapt interface and addresses before use.
- `scripts/mitm-setup-notes.md` — historical MITM, TLS, and observation notes. Commands there are not blanket authorization to change a host or device.

## References

- [Seagate GoFlex Home LED functionality](https://www.seagate.com/support/kb/goflex-home-led-functionality-3205en/)
- [Seagate remote-access discontinuation notice](https://www.seagate.com/support/kb/what-to-know-about-goflex-home-and-the-discontinuation-of-remote-access-007867en/)
- [Community firmware reflash procedure](http://goflexhome.blogspot.com/2019/01/firmware-reflash-without-seagateshare.html)
- [BeyondLogic archived recovery boot log](https://web.archive.org/web/2020id_/https://wiki.beyondlogic.org/index.php/Seagate_FreeAgent_GoFlex_Home_Firmare_Recovery)
- [OpenStora project](https://github.com/Dees7/openstora) — reference for the local sign-in route investigation.

Firmware files are not included in this repository because their provenance and redistribution rights are uncertain. This guide is for authorized recovery and reuse of your own device only.
