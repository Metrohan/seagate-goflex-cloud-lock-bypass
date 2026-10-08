#!/usr/bin/env python3
"""Plain HTTP observer used behind the legacy-TLS stunnel test service."""

import json
import re
import sys
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


REDACTED = "<redacted>"
MAX_BODY_BYTES = 65536
SUCCESS_XML = b'<?xml version="1.0"?><response code="0" status="ok"/>'
SENSITIVE_NAMES = {
    "api-key",
    "apikey",
    "authorization",
    "cookie",
    "pass",
    "passwd",
    "password",
    "proxy-authorization",
    "secret",
    "set-cookie",
    "token",
    "x-api-key",
}
TEXT_ATTRIBUTE_RE = re.compile(
    r"(?i)\b([A-Za-z0-9_-]*(?:pass|passwd|password|secret|token|api[-_]?key)"
    r"[A-Za-z0-9_-]*)"
    r"\s*=\s*"
    r"(\"[^\"]*\"|'[^']*'|[^\s&;,<>\"']+)"
)
# Sensitive XML element content, e.g. <token>SECRET</token>. Tag name is
# captured so the closing tag can be matched even with a namespace prefix.
TEXT_ELEMENT_RE = re.compile(
    r"(?is)(<\s*([A-Za-z0-9_:-]*(?:pass|passwd|password|secret|token|api[-_]?key)"
    r"[A-Za-z0-9_:-]*)\b[^>]*>)(.*?)(</\s*\2\s*>)"
)


def _redact_text_attribute(match):
    name, value = match.group(1), match.group(2)
    if value[:1] in ("\"", "'"):
        quote = value[0]
        return "{0}={1}{2}{1}".format(name, quote, REDACTED)
    return "{0}={1}".format(name, REDACTED)


def _redact_text_element(match):
    return match.group(1) + REDACTED + match.group(4)


def _is_sensitive(name):
    lowered = str(name).lower()
    return lowered in SENSITIVE_NAMES or lowered.endswith(
        ("passwd", "password", "secret", "token")
    )


def _redact_pairs(pairs):
    return [
        (name, REDACTED if _is_sensitive(name) else value)
        for name, value in pairs
    ]


def redact_url(url):
    parts = urlsplit(url)
    query = urlencode(_redact_pairs(parse_qsl(parts.query, keep_blank_values=True)))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


def redact_headers(headers):
    return {
        name: REDACTED if _is_sensitive(name) else value
        for name, value in headers.items()
    }


def _redact_json(value):
    if isinstance(value, dict):
        return {
            name: REDACTED if _is_sensitive(name) else _redact_json(item)
            for name, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_json(item) for item in value]
    return value


def summarize_body(body, content_type):
    media_type = content_type.split(";", 1)[0].strip().lower()

    if media_type == "application/x-www-form-urlencoded":
        try:
            text = body.decode("utf-8")
        except UnicodeDecodeError:
            return {"encoding": "unparsed", "length": len(body)}
        return urlencode(_redact_pairs(parse_qsl(text, keep_blank_values=True)))

    if media_type == "application/json" or media_type.endswith("+json"):
        try:
            return _redact_json(json.loads(body.decode("utf-8")))
        except (UnicodeDecodeError, ValueError):
            return {"encoding": "unparsed", "length": len(body)}

    # Axentra/HipServ devices are observed sending non-standard MIME types
    # (e.g. 'txt/xml' instead of 'text/xml') for otherwise-textual bodies.
    # Classify by subtype, not just the 'text/' prefix, so these are still
    # logged instead of silently falling through to the binary branch.
    subtype = media_type.rsplit("/", 1)[-1] if "/" in media_type else media_type
    is_text = (
        media_type.startswith("text/")
        or subtype == "xml"
        or subtype.endswith("+xml")
    )
    if is_text:
        try:
            text = body.decode("utf-8")
        except UnicodeDecodeError:
            return {"encoding": "binary", "length": len(body)}
        text = TEXT_ELEMENT_RE.sub(_redact_text_element, text)
        text = TEXT_ATTRIBUTE_RE.sub(_redact_text_attribute, text)
        return text

    return {"encoding": "binary", "length": len(body)}


class CatcherHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _content_length(self):
        raw_length = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_length)
        except ValueError:
            return None
        if length < 0:
            return None
        return length

    def _send_empty(self, status):
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True

    def _handle(self):
        length = self._content_length()
        if length is None:
            self._send_empty(400)
            return
        if length > MAX_BODY_BYTES:
            self._send_empty(413)
            return

        body = self.rfile.read(length) if length else b""
        content_type = self.headers.get("Content-Type", "")
        record = {
            "body": summarize_body(body, content_type),
            "body_length": len(body),
            "client": self.client_address[0],
            "headers": redact_headers(self.headers),
            "host": self.headers.get("Host", ""),
            "method": self.command,
            "path": redact_url(self.path),
            "timestamp": datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
            + "Z",
        }
        json.dump(record, self.server.log_stream, sort_keys=True)
        self.server.log_stream.write("\n")
        self.server.log_stream.flush()

        self.send_response(200)
        self.send_header("Content-Type", "application/xml")
        self.send_header("Content-Length", str(len(SUCCESS_XML)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(SUCCESS_XML)
        self.close_connection = True

    do_GET = _handle
    do_POST = _handle
    do_PUT = _handle

    def log_message(self, _format, *_args):
        pass


def make_server(address, port, log_stream=None):
    server = HTTPServer((address, port), CatcherHandler)
    server.log_stream = log_stream or sys.stdout
    return server


def main():
    internal_server = make_server("127.0.0.1", 18080)
    internal_thread = threading.Thread(target=internal_server.serve_forever)
    internal_thread.daemon = True
    internal_thread.start()

    public_server = make_server("0.0.0.0", 8080)
    try:
        public_server.serve_forever()
    finally:
        public_server.server_close()
        internal_server.shutdown()
        internal_server.server_close()
        internal_thread.join()


if __name__ == "__main__":
    main()
