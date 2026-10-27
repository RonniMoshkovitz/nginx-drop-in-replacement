#!/usr/bin/env python3
"""Regression test for CVE-2026-15176 (nginx alias+rewrite buffer overflow in
ngx_http_map_uri_to_path). Confirms the baseline still reproduces the bug and
the patched image's backport blocks it. Exits non-zero if the fix is missing,
broken, or either server stops responding.
"""
from __future__ import annotations

import sys
from pathlib import Path

from test_utils import BASELINE_IMAGE, PATCHED_IMAGE, NginxTestHarness, ensure_images_built, ro_mount

ROOT = Path(__file__).resolve().parent
REPRO_CONF = ROOT / "config" / "cve_2026_15176.conf"

ALERT_TEXT = '"alias" cannot be used in location "/foo/" where URI was rewritten'
SERVER_NAME = "cve-repro"


def probe(container: NginxTestHarness):
    return container.request("/foo/1", headers={"Host": SERVER_NAME})


def still_alive(container: NginxTestHarness) -> bool:
    status, _, _ = probe(container)
    return status is not None


def extract_request_filename(body: bytes) -> bytes:
    prefix = b"request_filename="
    if not body.startswith(prefix):
        raise ValueError(f"unexpected response body: {body!r}")
    return body[len(prefix):].rstrip(b"\n")


def probe_and_report(container: NginxTestHarness, label: str) -> tuple[bool, bytes | None]:
    status, _, body = probe(container)
    alert_logged = container.wait_for_log(ALERT_TEXT)

    if status is None:
        print(f"{label} : connection closed without a response (possible crash), alert logged={alert_logged}")
        return alert_logged, None

    try:
        filename = extract_request_filename(body)
    except ValueError as exc:
        print(f"{label} : HTTP {status}, {exc}, alert logged={alert_logged}")
        return alert_logged, None

    print(f"{label} : HTTP {status}, request_filename={filename!r}, alert logged={alert_logged}")
    return alert_logged, filename


def check_fix_evidence(b_alert: bool, b_filename: bytes | None, p_alert: bool, p_filename: bytes | None) -> list[str]:
    failures = []

    if b_alert:
        failures.append(
            "baseline unexpectedly logged the 'alias' alert -- either the "
            "baseline image changed, or this repro no longer matches the "
            "vulnerable code path."
        )

    if b_filename is None or b"\x00" not in b_filename:
        failures.append(
            f"baseline's request_filename ({b_filename!r}) did not contain "
            "corrupted/null memory as expected -- this repro's alias/rewrite "
            "length relationship may have stopped reliably triggering the "
            "unsigned-underflow code path; re-check against the upstream "
            "commit f8a23425bd6840c4c36b4264edf576ba3646156f."
        )

    if not p_alert:
        failures.append(
            "FIX NOT ACTIVE: patched image did not log the 'alias cannot "
            "be used...' alert -- the CVE-2026-15176 backport is missing "
            "or not taking effect."
        )

    if p_filename != b"":
        failures.append(
            f"FIX NOT ACTIVE: patched image's request_filename was "
            f"{p_filename!r}, expected empty (safe rejection)."
        )

    return failures


def check_liveness(baseline: NginxTestHarness, patched: NginxTestHarness) -> list[str]:
    b_alive, p_alive = still_alive(baseline), still_alive(patched)
    print(f"baseline responsive after the probe : {b_alive}")
    print(f"patched  responsive after the probe : {p_alive}")
    if b_alive and p_alive:
        return []
    return ["a server stopped responding after the probe (possible crash)."]


def report_result(failures: list[str]) -> int:
    if failures:
        print("\nFAIL:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1

    print(
        "\nbaseline reproduces the known-vulnerable behavior (no alert), "
        "patched image's backport is active (alert logged, safe empty result), "
        "neither server crashed."
    )
    return 0


def main() -> int:
    ensure_images_built(BASELINE_IMAGE, PATCHED_IMAGE)
    mount = ro_mount(REPRO_CONF, "/etc/nginx/conf.d/cve-repro.conf")

    print("CVE-2026-15176 regression check (alias + rewrite, backported fix)\n")

    with NginxTestHarness(BASELINE_IMAGE, ["-v", mount]) as baseline, \
            NginxTestHarness(PATCHED_IMAGE, ["-v", mount]) as patched:
        b_alert, b_filename = probe_and_report(baseline, "baseline")
        p_alert, p_filename = probe_and_report(patched, "patched ")

        failures = check_fix_evidence(b_alert, b_filename, p_alert, p_filename)
        failures += check_liveness(baseline, patched)

    return report_result(failures)


if __name__ == "__main__":
    sys.exit(main())
