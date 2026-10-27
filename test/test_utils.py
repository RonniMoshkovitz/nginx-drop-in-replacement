#!/usr/bin/env python3
"""This file contains utilities for Docker based nginx tests. It includs
NginxTestHarness, a context manager that boots a throwaway nginx container
and exposes simple HTTP helpers.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASELINE_IMAGE = os.environ.get("BASELINE_IMAGE", "nginx:1.25-bookworm")
PATCHED_IMAGE = os.environ.get("PATCHED_IMAGE", "nginx-patched:1.25-bookworm")

IGNORED_HEADERS = {"date", "connection", "keep-alive"}
LOOPBACK_HOST = "127.0.0.1"

CONNECT_TIMEOUT = 5.0       # for raw-socket connect, used by raw_tcp_request
REQUEST_TIMEOUT = 10.0      # for normal HTTP request, used by http_request
READY_PROBE_TIMEOUT = 1.0   # for single readiness-check request
READY_TIMEOUT_DEFAULT = 20.0  # for overall budget for a container to become ready


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    """Run a command, raising on a non-zero exit, capturing text output."""
    return subprocess.run(cmd, check=True, capture_output=True, text=True)


def image_present(name: str) -> bool:
    return bool(run(["docker", "images", "-q", name]).stdout.strip())


def ensure_images_built(*images: str) -> None:
    """Exit with a clear message if any of `images` hasn't been built yet."""
    missing = [image for image in images if not image_present(image)]
    if missing:
        raise SystemExit(f"{', '.join(missing)} not built yet -- run `make image` first")


def http_request(port: int, path: str, method: str = "GET", body: bytes | None = None,
                  headers: dict | None = None):
    """Returns (status, headers, body). If the connection drops before a response
    is readable it returns (None, {}, b"") instead of raising an error. This lets
    callers treat "no response" as a comparable outcome rather than a crash."""
    req = urllib.request.Request(
        f"http://{LOOPBACK_HOST}:{port}{path}", data=body, method=method, headers=headers or {},
    )
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()
    except (urllib.error.URLError, OSError):
        return None, {}, b""


def raw_tcp_request(port: int, raw_bytes: bytes):
    """Send bytes directly over a socket (used where urllib refuses to build a
    deliberately invalid HTTP/1.1 request)."""
    with socket.create_connection((LOOPBACK_HOST, port), timeout=CONNECT_TIMEOUT) as sock:
        sock.sendall(raw_bytes)
        sock.shutdown(socket.SHUT_WR)
        raw = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            raw += chunk

    head, _, body = raw.partition(b"\r\n\r\n")
    lines = head.split(b"\r\n")
    status_parts = lines[0].split()
    status = int(status_parts[1]) if len(status_parts) >= 2 and status_parts[1].isdigit() else None
    headers = {}
    for line in lines[1:]:
        if b":" in line:
            key, _, value = line.partition(b":")
            headers[key.decode("latin1").strip()] = value.decode("latin1").strip()
    return status, headers, body


def normalized_headers(headers: dict) -> dict:
    return {k.lower(): v for k, v in headers.items() if k.lower() not in IGNORED_HEADERS}


def ro_mount(host_path: str | Path, container_path: str) -> str:
    """Build a Docker `-v` read-only bind-mount spec string."""
    return f"{host_path}:{container_path}:ro"


class NginxTestHarness:
    """Context manager for a single throwaway nginx container under test,
    published on a random host loopback port."""

    def __init__(self, image: str, extra_args: list[str] | None = None):
        self.image = image
        self.extra_args = extra_args or []
        self.container_id: str | None = None
        self.port: int | None = None

    def __enter__(self) -> "NginxTestHarness":
        cmd = ["docker", "run", "-d", "--rm", "-p", f"{LOOPBACK_HOST}::80", *self.extra_args, self.image]
        self.container_id = run(cmd).stdout.strip()
        try:
            self.port = self._host_port()
            self._wait_until_ready()
        except Exception:
            self._remove_container()
            raise
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self._remove_container()

    def _remove_container(self) -> None:
        result = subprocess.run(["docker", "rm", "-f", self.container_id], capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Warning: failed to remove container {self.container_id}: {result.stderr.strip()}",
                  file=sys.stderr)

    def logs(self) -> str:
        result = run(["docker", "logs", self.container_id])
        return result.stdout + result.stderr

    def wait_for_log(self, text: str, timeout: float = 2.0, interval: float = 0.2) -> bool:
        """Poll the container's logs for `text`, allowing for log-driver buffering delay."""
        deadline = time.monotonic() + timeout
        while True:
            if text in self.logs():
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(interval)

    def request(self, path: str, method: str = "GET", body: bytes | None = None,
                headers: dict | None = None):
        return http_request(self.port, path, method=method, body=body, headers=headers)

    def raw_request(self, raw_bytes: bytes):
        return raw_tcp_request(self.port, raw_bytes)

    def _host_port(self) -> int:
        out = run(["docker", "port", self.container_id, "80"]).stdout.strip().splitlines()[0]
        return int(out.rsplit(":", 1)[1])

    def _wait_until_ready(self, timeout: float = READY_TIMEOUT_DEFAULT) -> None:
        deadline = time.monotonic() + timeout
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                urllib.request.urlopen(f"http://{LOOPBACK_HOST}:{self.port}/", timeout=READY_PROBE_TIMEOUT)
                return
            except urllib.error.HTTPError:
                return  # server answered -- a 4xx/5xx still means it's up
            except Exception as exc:  # noqa: BLE001 - connection refused while booting
                last_error = exc
                time.sleep(0.2)
        raise RuntimeError(f"Server on port {self.port} never became ready: {last_error}")
