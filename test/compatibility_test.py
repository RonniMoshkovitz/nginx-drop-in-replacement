#!/usr/bin/env python3
"""Compatibility test: issues identical HTTP requests at nginx:1.25-bookworm
and the patched image and asserts the responses (status, headers, body)
match byte-for-byte, excluding Date/Connection/Keep-Alive. TLS, performance,
and non-HTTP protocols are out of scope. Exits non-zero on the first mismatch.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import NamedTuple

from test_utils import (
    BASELINE_IMAGE,
    PATCHED_IMAGE,
    NginxTestHarness,
    ensure_images_built,
    normalized_headers,
    ro_mount,
)

ROOT = Path(__file__).resolve().parent
CUSTOM_CONF = ROOT / "config" / "nginx.conf"


class Case(NamedTuple):
    """One request to issue against a container. `raw`, if set, is sent as-is
    over a raw socket instead of building a normal HTTP request from path/method/body."""
    name: str
    path: str = ""
    method: str = "GET"
    body: bytes | None = None
    raw: bytes | None = None

DEFAULT_CASES = [
    Case("GET /", "/"),
    Case("GET /missing (404)", "/does-not-exist"),
    Case("HEAD /", "/", method="HEAD"),
    Case("POST 256KiB body", "/", method="POST", body=b"x" * (256 * 1024)),
    Case("POST 2MiB body (over client_max_body_size)", "/", method="POST", body=b"x" * (2 * 1024 * 1024)),
    Case("malformed request (HTTP/1.1, no Host header)", raw=b"GET / HTTP/1.1\r\n\r\n"),
]

CUSTOM_CONFIG_CASES = [
    Case("custom config: GET /ping", "/ping"),
    Case("custom config: GET /status", "/status"),
]

def run_case(container: NginxTestHarness, case: Case):
    if case.raw is not None:
        return container.raw_request(case.raw)
    return container.request(case.path, method=case.method, body=case.body)


def fail(case: str, detail: str) -> None:
    raise SystemExit(f"FAIL [{case}]: {detail}")


def assert_match(case: str, baseline_result, patched_result) -> None:
    b_status, b_headers, b_body = baseline_result
    p_status, p_headers, p_body = patched_result

    if b_status != p_status:
        fail(case, f"status {b_status} (baseline) != {p_status} (patched)")
    if b_body != p_body:
        fail(case, f"body mismatch: {len(b_body)} bytes (baseline) vs {len(p_body)} bytes (patched)")
    nb_headers = normalized_headers(b_headers)
    np_headers = normalized_headers(p_headers)
    if nb_headers != np_headers:
        fail(case, f"headers differ: baseline={nb_headers} patched={np_headers}")
    print(f"match: {case} -> status {b_status}, {len(b_body)} body bytes, headers equal")


def run_matrix(baseline: NginxTestHarness, patched: NginxTestHarness, cases: list[Case]) -> None:
    for case in cases:
        assert_match(case.name, run_case(baseline, case), run_case(patched, case))


def main() -> int:
    ensure_images_built(BASELINE_IMAGE, PATCHED_IMAGE)

    print(f"running the request matrix on {BASELINE_IMAGE} (baseline) and {PATCHED_IMAGE} (patched)\n")

    print("-- default config --")
    with NginxTestHarness(BASELINE_IMAGE) as baseline, NginxTestHarness(PATCHED_IMAGE) as patched:
        run_matrix(baseline, patched, DEFAULT_CASES)

    print("\n-- custom config (test/config/nginx.conf) --")
    mount = ro_mount(CUSTOM_CONF, "/etc/nginx/conf.d/default.conf")
    with NginxTestHarness(BASELINE_IMAGE, ["-v", mount]) as baseline, \
            NginxTestHarness(PATCHED_IMAGE, ["-v", mount]) as patched:
        run_matrix(baseline, patched, CUSTOM_CONFIG_CASES)

    print("\nevery case behaved identically on both images")
    return 0


if __name__ == "__main__":
    sys.exit(main())
