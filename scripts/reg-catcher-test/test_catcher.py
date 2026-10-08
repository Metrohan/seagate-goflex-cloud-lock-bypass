#!/usr/bin/env python3
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import catcher


EXPECTED_XML = b'<?xml version="1.0"?><response code="0" status="ok"/>'
TEST_DIR = Path(__file__).resolve().parent


class RedactionTests(unittest.TestCase):
    def test_redacts_mixed_case_query_secret(self):
        got = catcher.redact_url(
            "/register?serial=SERIAL&PaSs=SECRET&subdomain=demo"
        )

        self.assertEqual(
            got,
            "/register?serial=SERIAL&PaSs=%3Credacted%3E&subdomain=demo",
        )

    def test_redacts_form_body_and_keeps_observation_fields(self):
        got = catcher.summarize_body(
            b"serialnum=SERIAL&token=SECRET&subdomain=demo",
            "application/x-www-form-urlencoded",
        )

        self.assertEqual(
            got,
            "serialnum=SERIAL&token=%3Credacted%3E&subdomain=demo",
        )

    def test_invalid_utf8_form_is_summarized_without_crashing(self):
        got = catcher.summarize_body(
            b"token=\xff",
            "application/x-www-form-urlencoded",
        )

        self.assertEqual(got, {"encoding": "unparsed", "length": 7})

    def test_redacts_camel_case_token_field(self):
        got = catcher.summarize_body(
            b"serialnum=SERIAL&registrationToken=SECRET",
            "application/x-www-form-urlencoded",
        )

        self.assertEqual(
            got,
            "serialnum=SERIAL&registrationToken=%3Credacted%3E",
        )

    def test_redacts_password_and_api_key_name_variants(self):
        got = catcher.summarize_body(
            b"adminPassword=SECRET1&apiKey=SECRET2&serialnum=SERIAL",
            "application/x-www-form-urlencoded",
        )

        self.assertEqual(
            got,
            "adminPassword=%3Credacted%3E&apiKey=%3Credacted%3E&serialnum=SERIAL",
        )

    def test_redacts_nested_json_secret(self):
        got = catcher.summarize_body(
            b'{"serialnum":"SERIAL","auth":{"password":"SECRET"}}',
            "application/json; charset=utf-8",
        )

        self.assertEqual(
            got,
            {"serialnum": "SERIAL", "auth": {"password": "<redacted>"}},
        )

    def test_malformed_json_is_summarized_without_raw_content(self):
        got = catcher.summarize_body(
            b'{"token":"SECRET"',
            "application/json",
        )

        self.assertEqual(got, {"encoding": "unparsed", "length": 17})

    def test_redacts_sensitive_headers_case_insensitively(self):
        got = catcher.redact_headers(
            {
                "Host": "reg.example",
                "Authorization": "Basic SECRET",
                "COOKIE": "session=SECRET",
                "Proxy-Authorization": "Basic SECRET2",
            }
        )

        self.assertEqual(
            got,
            {
                "Host": "reg.example",
                "Authorization": "<redacted>",
                "COOKIE": "<redacted>",
                "Proxy-Authorization": "<redacted>",
            },
        )

    def test_binary_body_is_not_logged_raw(self):
        got = catcher.summarize_body(
            b"\x00SECRET\xff",
            "application/octet-stream",
        )

        self.assertEqual(got, {"encoding": "binary", "length": 8})

    def test_redacts_secret_assignment_in_plain_text(self):
        got = catcher.summarize_body(
            b"serial=SERIAL pass=SECRET registrationToken=SECRET2 subdomain=demo",
            "text/plain",
        )

        self.assertEqual(
            got,
            "serial=SERIAL pass=<redacted> registrationToken=<redacted> subdomain=demo",
        )

    def test_redacts_nonstandard_txt_slash_xml_content_type(self):
        # Gerçek GoFlex Home cihazı 'Content-Type: txt/xml' (standart olmayan,
        # 'text/xml' değil) gönderiyor. 2026-09-25 gerçek reboot testinde bu
        # yüzden POST /rest/1.0/status/hipserv gövdesi 'binary' sayılıp
        # kayboldu. Bu regresyonu bir daha yaşamamak için burada sabitleniyor.
        got = catcher.summarize_body(
            b'<hipserv serial="SERIAL" pass="SECRET"><status>ok</status></hipserv>',
            "txt/xml",
        )

        self.assertEqual(
            got,
            '<hipserv serial="SERIAL" pass="<redacted>"><status>ok</status></hipserv>',
        )

    def test_redacts_application_xml_element_value_secret(self):
        got = catcher.summarize_body(
            b"<root><token>SECRET</token><serial>SERIAL</serial></root>",
            "application/xml; charset=utf-8",
        )

        self.assertEqual(
            got,
            "<root><token><redacted></token><serial>SERIAL</serial></root>",
        )


class HttpBehaviorTests(unittest.TestCase):
    def setUp(self):
        self.logs = io.StringIO()

    class NonClosingBytesIO(io.BytesIO):
        def close(self):
            pass

    class MemoryConnection(object):
        def __init__(self, request_bytes):
            self.input = HttpBehaviorTests.NonClosingBytesIO(request_bytes)
            self.output = HttpBehaviorTests.NonClosingBytesIO()

        def makefile(self, mode, _buffering=None):
            return self.input if "r" in mode else self.output

        def sendall(self, data):
            self.output.write(data)

    class MemoryServer(object):
        def __init__(self, log_stream):
            self.log_stream = log_stream

    def request(self, method, path, body=None, headers=None):
        body = body or b""
        request_headers = dict(headers or {})
        request_headers.setdefault("Host", "local-test")
        if body and not any(
            name.lower() == "content-length" for name in request_headers
        ):
            request_headers["Content-Length"] = str(len(body))
        lines = ["{} {} HTTP/1.1".format(method, path)]
        lines.extend(
            "{}: {}".format(name, value)
            for name, value in request_headers.items()
        )
        raw_request = ("\r\n".join(lines) + "\r\n\r\n").encode("ascii") + body
        connection = self.MemoryConnection(raw_request)
        catcher.CatcherHandler(
            connection,
            ("local-test", 0),
            self.MemoryServer(self.logs),
        )
        raw_response = connection.output.getvalue()
        raw_headers, response_body = raw_response.split(b"\r\n\r\n", 1)
        header_lines = raw_headers.decode("iso-8859-1").split("\r\n")
        status = int(header_lines[0].split(" ", 2)[1])
        response_headers = dict(
            line.split(": ", 1) for line in header_lines[1:]
        )
        return status, response_headers, response_body

    def test_get_returns_xml_success(self):
        status, headers, body = self.request(
            "GET",
            "/cpestatus?serial=SERIAL&pass=SECRET",
            headers={"Host": "cpestatus.example"},
        )

        self.assertEqual(status, 200)
        self.assertEqual(body, EXPECTED_XML)

    def test_post_returns_framed_xml_and_redacted_log(self):
        status, headers, body = self.request(
            "POST",
            "/register?token=QUERYSECRET",
            b"serialnum=SERIAL&pass=BODYSECRET&subdomain=demo",
            {
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": "Basic HEADERSECRET",
                "Host": "reg.example",
            },
        )

        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "application/xml")
        self.assertEqual(int(headers["Content-Length"]), len(EXPECTED_XML))
        self.assertEqual(headers["Connection"], "close")
        self.assertEqual(body, EXPECTED_XML)
        record = json.loads(self.logs.getvalue().strip())
        rendered = json.dumps(record, sort_keys=True)
        self.assertIn("<redacted>", rendered)
        self.assertNotIn("QUERYSECRET", rendered)
        self.assertNotIn("BODYSECRET", rendered)
        self.assertNotIn("HEADERSECRET", rendered)
        self.assertEqual(record["host"], "reg.example")
        self.assertEqual(record["method"], "POST")

    def test_put_returns_xml_success(self):
        status, _headers, body = self.request(
            "PUT",
            "/device",
            b'{"token":"SECRET","state":"ready"}',
            {"Content-Type": "application/json", "Host": "axentra.example"},
        )

        self.assertEqual(status, 200)
        self.assertEqual(body, EXPECTED_XML)

    def test_invalid_content_length_returns_400_and_server_survives(self):
        status, _headers, _body = self.request(
            "POST",
            "/register",
            b"",
            {"Content-Length": "invalid", "Host": "reg.example"},
        )

        self.assertEqual(status, 400)
        followup_status, _headers, _body = self.request("GET", "/health")
        self.assertEqual(followup_status, 200)

    def test_oversized_content_length_returns_413_and_server_survives(self):
        status, _headers, _body = self.request(
            "POST",
            "/register",
            b"",
            {"Content-Length": "65537", "Host": "reg.example"},
        )

        self.assertEqual(status, 413)
        followup_status, _headers, _body = self.request("GET", "/health")
        self.assertEqual(followup_status, 200)

    def test_negative_content_length_returns_400(self):
        status, _headers, _body = self.request(
            "POST",
            "/register",
            b"",
            {"Content-Length": "-1", "Host": "reg.example"},
        )

        self.assertEqual(status, 400)


class RuntimeContractTests(unittest.TestCase):
    def test_dockerfile_uses_fresh_jessie_base_without_embedding_keys(self):
        dockerfile = (TEST_DIR / "Dockerfile").read_text()

        self.assertIn("FROM debian:8", dockerfile)
        self.assertNotIn("FROM goflex-legacy-ssl-clean:test", dockerfile)
        self.assertIn("openssl python3 stunnel4", dockerfile)
        self.assertNotIn("python3-minimal", dockerfile)
        self.assertNotIn("COPY cert.pem", dockerfile)
        self.assertNotIn("COPY key.pem", dockerfile)
        self.assertNotIn("goflex-legacy-ssl\n", dockerfile)

    def test_stunnel_forwards_legacy_https_only_to_loopback_catcher(self):
        config = (TEST_DIR / "stunnel.conf").read_text()

        self.assertIn("accept = 0.0.0.0:8443", config)
        self.assertIn("connect = 127.0.0.1:18080", config)
        self.assertIn("cert = /cert.pem", config)
        self.assertIn("key = /key.pem", config)

    def test_entrypoint_checks_mounts_before_starting_services(self):
        entrypoint = (TEST_DIR / "entrypoint.sh").read_text()

        cert_check = entrypoint.index('[ -r /cert.pem ]')
        key_check = entrypoint.index('[ -r /key.pem ]')
        catcher_start = entrypoint.index("python3 /opt/goflex/catcher.py")
        stunnel_start = entrypoint.index("stunnel4 /etc/stunnel/stunnel.conf")
        self.assertLess(cert_check, catcher_start)
        self.assertLess(key_check, catcher_start)
        self.assertLess(catcher_start, stunnel_start)

    def test_entrypoint_refuses_missing_certificate_mounts(self):
        result = subprocess.run(
            ["sh", str(TEST_DIR / "entrypoint.sh")],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("/cert.pem", result.stderr)


class OperatorScriptSafetyTests(unittest.TestCase):
    def make_fixture(self, include_certificates):
        tempdir = tempfile.TemporaryDirectory()
        root = Path(tempdir.name)
        script_dir = root / "scripts" / "reg-catcher-test"
        script_dir.mkdir(parents=True)
        shutil.copy(
            str(TEST_DIR / "build-run-test.sh"),
            str(script_dir / "build-run-test.sh"),
        )
        if include_certificates:
            (root / "cert.pem").write_text("test certificate\n")
            (root / "key.pem").write_text("test key\n")

        fake_bin = root / "fake-bin"
        fake_bin.mkdir()
        fake_docker = fake_bin / "docker"
        fake_docker.write_text(
            "#!/bin/sh\n"
            "printf '%s\\n' \"$*\" >> \"$FAKE_DOCKER_LOG\"\n"
            "if [ \"$1 $2\" = \"container inspect\" ]; then\n"
            "    exit \"${FAKE_INSPECT_EXIT:-1}\"\n"
            "fi\n"
            "exit 0\n"
        )
        fake_docker.chmod(0o755)
        log_path = root / "docker-invocations.log"
        environment = dict(os.environ)
        environment["PATH"] = str(fake_bin) + os.pathsep + environment["PATH"]
        environment["FAKE_DOCKER_LOG"] = str(log_path)
        return tempdir, script_dir / "build-run-test.sh", log_path, environment

    def test_existing_test_container_stops_without_destructive_docker_call(self):
        tempdir, script, log_path, environment = self.make_fixture(True)
        self.addCleanup(tempdir.cleanup)
        environment["FAKE_INSPECT_EXIT"] = "0"

        result = subprocess.run(
            ["sh", str(script)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            env=environment,
        )

        self.assertNotEqual(result.returncode, 0)
        invocations = log_path.read_text()
        self.assertIn("container inspect goflex-reg-catcher-test", invocations)
        self.assertNotIn("goflex-legacy-ssl", invocations)
        for destructive_word in (" stop ", " rm ", " rename "):
            self.assertNotIn(destructive_word, " " + invocations + " ")

    def test_missing_certificates_stops_before_docker(self):
        tempdir, script, log_path, environment = self.make_fixture(False)
        self.addCleanup(tempdir.cleanup)

        result = subprocess.run(
            ["sh", str(script)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            env=environment,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("cert.pem", result.stderr)
        self.assertFalse(log_path.exists())


if __name__ == "__main__":
    unittest.main()
