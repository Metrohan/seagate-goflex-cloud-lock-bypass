# GoFlex Legacy TLS Registration Catcher Test Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a production-isolated legacy TLS terminator and dynamic HTTP catcher that logs redacted GoFlex registration requests and returns a generic XML success response.

**Architecture:** A Debian Jessie-derived test image runs OpenSSL-1.0.1-linked `stunnel` on container port 8443 and forwards plaintext to a Python HTTP server on loopback port 18080. The same catcher exposes container port 8080 for direct HTTP tests; an operator script publishes both ports only on host loopback and never references the production container.

**Tech Stack:** Debian Jessie, OpenSSL 1.0.1, stunnel4, Python 3 standard library, POSIX shell, Docker CLI.

**Spec:** `docs/superpowers/specs/2026-09-25-reg-catcher-test-design.md`

## Global Constraints

- Do not run Docker commands from the Codex sandbox; Claude runs them in a separate shell.
- Do not stop, rename, remove, or replace `goflex-legacy-ssl`.
- Do not change host networking, dnsmasq, or iptables.
- Do not request a device reboot during this implementation phase.
- Do not put the real serial, pass/token, LAN IP, or hipname in repository files or tests.
- Do not copy certificates or private keys into the image; mount them read-only at runtime.
- Do not commit or push; retain all existing uncommitted human work.
- Test container names and published ports are fixed to the isolated values in the approved spec.

## Review Focus

- A query or form field with mixed-case secret names must be redacted rather than logged verbatim; Task 1 tests mixed-case key matching.
- A malformed or oversized `Content-Length` must return a controlled client error without killing the server; Task 1 tests both cases.
- JSON and form bodies must retain useful non-secret fields while redacting secrets; Task 1 tests both encodings.
- Binary or undecodable bodies must not crash or emit raw bytes; Task 1 tests the binary summary.
- An existing test container must make the operator script stop without removing or replacing it; Task 3 requires Claude to exercise that branch with a deliberately retained test container.

---

### Task 1: Dynamic Catcher and Behavior Tests

**Files:**
- Create: `scripts/reg-catcher-test/test_catcher.py`
- Create: `scripts/reg-catcher-test/catcher.py`

**Interfaces:**
- Consumes: Python 3.4+ standard library only.
- Produces: `redact_url(url: str) -> str`, `redact_headers(headers) -> dict`, `summarize_body(body: bytes, content_type: str) -> object`, `make_server(address, port) -> HTTPServer`, and executable dual listeners on `127.0.0.1:18080` plus `0.0.0.0:8080`.

- [ ] **Step 1: Write failing redaction tests**

Create `test_catcher.py` with literal expectations proving that query parameters, form fields, JSON keys, authorization/cookie headers, mixed-case secret keys, and binary bodies are safely summarized. Use only `unittest`; import `catcher` from the same directory.

```python
def test_redacts_mixed_case_query_secret(self):
    got = catcher.redact_url('/register?serial=REDACTED&PaSs=REDACTED&subdomain=demo')
    self.assertEqual(got, '/register?serial=REDACTED&PaSs=REDACTED&subdomain=demo')

def test_redacts_form_body_and_keeps_observation_fields(self):
    got = catcher.summarize_body(
        b'serialnum=REDACTED&token=REDACTED&subdomain=demo',
        'application/x-www-form-urlencoded',
    )
    self.assertEqual(got, 'serialnum=REDACTED&token=REDACTED&subdomain=demo')

def test_binary_body_is_not_logged_raw(self):
    got = catcher.summarize_body(b'\x00SECRET\xff', 'application/octet-stream')
    self.assertEqual(got, {'encoding': 'binary', 'length': 8})
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```sh
python3 -m unittest discover -s scripts/reg-catcher-test -p 'test_*.py' -v
```

Expected: import or attribute failures because `catcher.py` and its public functions do not exist yet.

- [ ] **Step 3: Implement minimal redaction helpers**

Implement case-insensitive sensitive-name matching for `pass`, `password`, `passwd`, `token`, `authorization`, `cookie`, `set-cookie`, `secret`, and names ending in `_token`. Parse query/form data with `urllib.parse`; parse JSON with `json`; return a length-only dictionary for binary/undecodable content. Avoid f-strings so the file remains compatible with Jessie Python 3.4.

- [ ] **Step 4: Run tests and verify GREEN**

Run the Task 1 unittest command. Expected: redaction tests pass with no warning or traceback.

- [ ] **Step 5: Write failing HTTP behavior tests**

Start a real ephemeral `HTTPServer` in a test thread and use `http.client` to assert:

```python
EXPECTED_XML = b'<?xml version="1.0"?><response code="0" status="ok"/>'

def test_post_returns_framed_xml_success(self):
    status, headers, body = self.request(
        'POST', '/register', b'serialnum=REDACTED&pass=REDACTED',
        {'Content-Type': 'application/x-www-form-urlencoded', 'Host': 'reg.example'},
    )
    self.assertEqual(status, 200)
    self.assertEqual(headers['Content-Type'], 'application/xml')
    self.assertEqual(int(headers['Content-Length']), len(EXPECTED_XML))
    self.assertEqual(headers['Connection'], 'close')
    self.assertEqual(body, EXPECTED_XML)
```

Add separate tests for GET, PUT, invalid `Content-Length`, a body larger than 64 KiB, and a captured JSON log record that contains `<redacted>` but not the synthetic secret.

- [ ] **Step 6: Run HTTP tests and verify RED**

Run the Task 1 unittest command. Expected: failures because the request handler and `make_server` are missing.

- [ ] **Step 7: Implement the HTTP handler and dual-listener main**

Use `BaseHTTPRequestHandler` with `do_GET`, `do_POST`, and `do_PUT` delegating to one handler. Enforce a 65,536-byte body limit, emit one JSON object per request to stdout, set the exact XML response headers, suppress the framework's raw request logging, and start the internal TLS target in a daemon thread before serving port 8080 in the main thread.

- [ ] **Step 8: Run tests and verify GREEN**

Run:

```sh
python3 -m unittest discover -s scripts/reg-catcher-test -p 'test_*.py' -v
```

Expected: all catcher unit/integration tests pass.

- [ ] **Step 9: Record a no-commit checkpoint**

Run `git diff --check` and `git status --short`. Do not stage or commit.

### Task 2: Legacy TLS Container Runtime

**Files:**
- Create: `scripts/reg-catcher-test/Dockerfile`
- Create: `scripts/reg-catcher-test/stunnel.conf`
- Create: `scripts/reg-catcher-test/entrypoint.sh`

**Interfaces:**
- Consumes: public/cacheable `debian:8` base, runtime mounts `/cert.pem:ro` and `/key.pem:ro`, catcher executable from Task 1.
- Produces: fresh `debian:8`-based image with container listeners `8080/tcp` and `8443/tcp`; stunnel forwards `8443 -> 127.0.0.1:18080`.

- [ ] **Step 1: Add static/runtime contract tests before configuration**

Extend `test_catcher.py` with tests that load the future files and assert externally meaningful safety contracts: the Dockerfile uses a fresh `debian:8` base so it cannot inherit previously copied keys; it never copies `cert.pem` or `key.pem`; stunnel accepts 8443 and connects only to loopback 18080; entrypoint refuses missing certificate/key and starts catcher before stunnel. These tests should fail because the files do not exist.

- [ ] **Step 2: Run tests and verify RED**

Run the Task 1 unittest command. Expected: `FileNotFoundError` for runtime files.

- [ ] **Step 3: Write the minimal Dockerfile**

Base on fresh `debian:8`; rewrite Jessie archive sources with `trusted=yes`; install only `openssl`, the full `python3` meta-package (including the matching standard library), and `stunnel4`; copy catcher/config/entrypoint; mark the entrypoint executable; expose 8080 and 8443. Do not use `python3-minimal`, `COPY cert.pem`, `COPY key.pem`, `ENV GOFLEX_*`, or production container names.

- [ ] **Step 4: Write stunnel and PID-1 process configuration**

Configure stunnel with `foreground = yes`, `client = no`, `accept = 0.0.0.0:8443`, `connect = 127.0.0.1:18080`, certificate/key mount paths, and diagnostic logging to stderr/stdout. In `entrypoint.sh`, validate readable mounts, start catcher, install TERM/INT/EXIT cleanup traps, start stunnel, fail if either child exits unexpectedly, and propagate a non-zero exit.

- [ ] **Step 5: Run tests and shell syntax checks**

Run:

```sh
python3 -m unittest discover -s scripts/reg-catcher-test -p 'test_*.py' -v
sh -n scripts/reg-catcher-test/entrypoint.sh
```

Expected: all tests pass and `sh -n` exits 0.

- [ ] **Step 6: Record a no-commit checkpoint**

Run `git diff --check` and `git status --short`. Do not stage or commit.

### Task 3: Safe Operator Workflow and Documentation

**Files:**
- Create: `scripts/reg-catcher-test/build-run-test.sh`
- Create: `scripts/reg-catcher-test/README.md`
- Modify: `.gitignore`
- Modify: `scripts/mitm-setup-notes.md`

**Interfaces:**
- Consumes: Task 1 catcher, Task 2 image inputs, repo-root `cert.pem` and `key.pem` supplied locally.
- Produces: exact build/run/test commands for Claude and a Turkish evidence record; no production mutation commands.

- [ ] **Step 1: Write failing operator safety tests**

Extend `test_catcher.py` to assert the future operator script's observable contract through a fake `docker` executable placed first in `PATH`: when `docker container inspect goflex-reg-catcher-test` returns success, the script exits non-zero and the fake invocation log contains no `stop`, `rm`, `rename`, or `goflex-legacy-ssl` command. Add a missing-cert test that exits before invoking Docker.

- [ ] **Step 2: Run tests and verify RED**

Run the Task 1 unittest command. Expected: failure because `build-run-test.sh` does not exist.

- [ ] **Step 3: Implement the safe build/run/test script**

Use fixed names `goflex-reg-catcher:test` and `goflex-reg-catcher-test`. Resolve the repo root from the script location; require readable `cert.pem` and `key.pem`; stop if the test container name already exists; then run:

```sh
docker build -t goflex-reg-catcher:test scripts/reg-catcher-test
docker run --name goflex-reg-catcher-test \
  -p 127.0.0.1:18080:8080 \
  -p 127.0.0.1:18443:8443 \
  -v "$REPO_ROOT/cert.pem:/cert.pem:ro" \
  -v "$REPO_ROOT/key.pem:/key.pem:ro" \
  -d goflex-reg-catcher:test
```

After startup, run synthetic HTTP and HTTPS GET/POST checks with non-secret fixture values, verify the XML body and container running state, and print manual log-inspection commands. Do not add cleanup, host networking, restart policy, production names, or reboot instructions.

- [ ] **Step 4: Run tests and syntax checks**

Run:

```sh
python3 -m unittest discover -s scripts/reg-catcher-test -p 'test_*.py' -v
sh -n scripts/reg-catcher-test/entrypoint.sh
sh -n scripts/reg-catcher-test/build-run-test.sh
```

Expected: all tests and both syntax checks pass without Docker access.

- [ ] **Step 5: Write operator README and Git ignores**

Document prerequisites, the exact single-script command, equivalent manual build/run/test commands, expected XML, redacted log inspection, the no-production/no-reboot boundary, and how Claude should report failures. Extend `.gitignore` without removing existing entries to cover `/cert.pem`, `/key.pem`, `scripts/*.log`, and test-generated artifacts.

- [ ] **Step 6: Update MITM experiment notes**

Append a dated Turkish section to `scripts/mitm-setup-notes.md` explaining why static `s_server -HTTP` cannot observe unknown POST/query paths, why stunnel separates legacy TLS from dynamic HTTP, what was implemented, which checks Codex could run, which Docker checks remain for Claude, and that production/device state was untouched.

- [ ] **Step 7: Run full local verification**

Run:

```sh
python3 -m unittest discover -s scripts/reg-catcher-test -p 'test_*.py' -v
sh -n scripts/reg-catcher-test/entrypoint.sh
sh -n scripts/reg-catcher-test/build-run-test.sh
git diff --check
git status --short
```

Expected: tests and syntax/diff checks pass; status shows only pre-existing work plus this task's new/modified files. Explicitly report that Docker build/run and real legacy ClientHello remain unverified in this sandbox.

- [ ] **Step 8: Hand off exact Claude commands**

Give Claude the exact manual command list from the README. Ask for build output, container status, synthetic test output, a redacted log excerpt, and stunnel/OpenSSL version evidence. Do not propose production replacement or device reboot until those results return and a separate production approval is granted.
