"""
diagnostics.py — Automatic diagnostics collector.

Called when a TCP probe fails. Collects ping, DNS resolution, traceroute,
HTTP/Curl details, and DNS query verification to help engineers troubleshoot
network issues.

Uses only Python stdlib (subprocess + socket + urllib) — no third-party libs.
"""

import os
import socket
import subprocess
import sys
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict


def run_ping(host: str) -> str:
    """
    Send a single ICMP ping to host and return a one-line summary.

    Uses platform-appropriate flags:
      Windows  — ping -n 1 -w 1000
      Linux    — ping -c 1 -W 1
    """
    if sys.platform == "win32":
        cmd = ["ping", "-n", "1", "-w", "1000", host]
    else:
        cmd = ["ping", "-c", "1", "-W", "1", host]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=5,
        )
        output = (result.stdout + result.stderr).strip()
        lines = [ln.strip() for ln in output.splitlines() if ln.strip()]
        return lines[-1] if lines else "no output"
    except subprocess.TimeoutExpired:
        return "ping timed out"
    except FileNotFoundError:
        return "ping command not found"
    except Exception as exc:
        return f"ping error: {exc}"


def run_dns(host: str) -> str:
    """
    Resolve host to IP addresses and return a compact summary string.
    Example: "google.com -> 142.250.185.46, 2607:f8b0:4004:c09::65"
    """
    try:
        results = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
        addrs = sorted({r[4][0] for r in results})
        return f"{host} -> {', '.join(addrs)}"
    except socket.gaierror as exc:
        return f"dns failed: {exc}"
    except Exception as exc:
        return f"dns error: {exc}"


def run_traceroute(host: str) -> str:
    """
    Execute a traceroute to the host with a limit of 10 hops for speed.
    """
    if sys.platform == "win32":
        cmd = ["tracert", "-d", "-h", "10", host]
    else:
        cmd = ["traceroute", "-n", "-m", "10", host]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=15,
        )
        return (result.stdout + result.stderr).strip()
    except subprocess.TimeoutExpired:
        return "traceroute timed out"
    except FileNotFoundError:
        if sys.platform != "win32":
            # Try tracepath as a fallback on Linux
            try:
                result = subprocess.run(
                    ["tracepath", "-n", "-m", "10", host],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                return (result.stdout + result.stderr).strip()
            except Exception:
                pass
        return "traceroute command not found"
    except Exception as exc:
        return f"traceroute error: {exc}"


def run_http_diagnostic(host: str, port: int) -> str:
    """
    Capture HTTP status, response headers, and response snippet for HTTP targets.
    """
    if port not in (80, 443, 8080, 8443):
        return f"Not applicable: Port {port} is not a standard HTTP port."

    scheme = "https" if port in (443, 8443) else "http"
    url = f"{scheme}://{host}:{port}/"
    
    headers = {"User-Agent": "Cypher-Agent-Diagnostic"}
    req = urllib.request.Request(url, headers=headers, method="GET")
    
    start_time = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            latency = (time.perf_counter() - start_time) * 1000
            status_code = response.status
            resp_headers = dict(response.headers)
            body_snippet = response.read(200).decode("utf-8", errors="replace")
            
            headers_str = "\n".join(f"  {k}: {v}" for k, v in resp_headers.items())
            return (
                f"GET {url} succeeded in {latency:.1f}ms\n"
                f"Status Code: {status_code}\n"
                f"Response Headers:\n{headers_str}\n\n"
                f"Response Snippet:\n{body_snippet}"
            )
    except urllib.error.HTTPError as e:
        latency = (time.perf_counter() - start_time) * 1000
        headers_str = "\n".join(f"  {k}: {v}" for k, v in e.headers.items()) if e.headers else ""
        try:
            body_snippet = e.read(200).decode("utf-8", errors="replace")
        except Exception:
            body_snippet = "could not read body"
        return (
            f"GET {url} failed with HTTP Status {e.code} in {latency:.1f}ms\n"
            f"Response Headers:\n{headers_str}\n\n"
            f"Response Snippet:\n{body_snippet}"
        )
    except Exception as e:
        return f"GET {url} failed: {e}"


def run_dns_verification(host: str) -> str:
    """
    Differentiates local DNS health from target domain DNS failure.
    Resolves the host locally and resolves global servers as control variables.
    """
    control_host = os.getenv("DNS_CONTROL_HOST", "google.com")

    # 1. Resolve host
    target_resolved = False
    target_ips = []
    try:
        results = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
        target_ips = sorted({r[4][0] for r in results})
        target_resolved = True
    except socket.gaierror:
        pass

    # 2. Resolve global control resolver to verify network DNS works
    control_resolved = False
    control_ips = []
    try:
        results = socket.getaddrinfo(control_host, None, proto=socket.IPPROTO_TCP)
        control_ips = sorted({r[4][0] for r in results})
        control_resolved = True
    except socket.gaierror:
        pass

    if target_resolved:
        return (
            f"Target host '{host}' DNS resolution is healthy.\n"
            f"Resolved IPs: {', '.join(target_ips)}"
        )
    else:
        if control_resolved:
            return (
                f"DNS Query Verification: FAIL\n"
                f"Detail: Local DNS resolver was able to resolve control host '{control_host}' -> {control_ips},\n"
                f"but failed to resolve target host '{host}'.\n"
                f"Conclusion: Target domain DNS registry is misconfigured or target is invalid/inactive."
            )
        else:
            return (
                f"DNS Query Verification: FAIL\n"
                f"Detail: Local DNS resolver failed to resolve both target host '{host}'\n"
                f"and control host '{control_host}'.\n"
                f"Conclusion: Local DNS resolver is offline, or agent has lost local gateway/network internet access."
            )


def collect(host: str, port: int, error: str = "TCP connection failed") -> Dict[str, str]:
    """
    Collect all diagnostics for a failed target concurrently.

    Args:
        host:  The hostname (no port) extracted from the target string.
        port:  The port number.
        error: Short description of the original failure reason.

    Returns:
        {"ping": ..., "dns": ..., "error": ..., "traceroute": ..., "http": ..., "dns_verification": ...}
    """
    # Run diagnostics in parallel to reduce total collection time
    results = {}
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {
            pool.submit(run_ping, host): "ping",
            pool.submit(run_dns, host): "dns",
            pool.submit(run_traceroute, host): "traceroute",
            pool.submit(run_http_diagnostic, host, port): "http",
            pool.submit(run_dns_verification, host): "dns_verification",
        }
        for future in as_completed(futures):
            key = futures[future]
            try:
                results[key] = future.result()
            except Exception as exc:
                results[key] = f"{key} error: {exc}"

    results["error"] = error
    return results
