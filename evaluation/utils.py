"""
Utility functions for benchmarking metadata, commit tracking, artifact persistence,
and network latency instrumentation.
"""
import os
import time
import subprocess
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Tuple, Dict, Any, List
import pandas as pd
import requests
import httpx


class APILatencyStats:
    """Aggregates round-trip HTTP request latencies, payload sizes, and status codes."""

    def __init__(self):
        self.latencies_ms: List[float] = []
        self.payload_bytes: List[int] = []
        self.status_codes: List[int] = []
        self.failed_requests: int = 0

    def record(self, duration_sec: float, payload_size: int = 0, status_code: int = 200) -> None:
        self.latencies_ms.append(duration_sec * 1000.0)
        self.payload_bytes.append(payload_size)
        self.status_codes.append(status_code)
        if status_code >= 400:
            self.failed_requests += 1

    def summary(self, wall_clock_sec: float = 0.0) -> Dict[str, Any]:
        if not self.latencies_ms:
            return {
                "request_count": 0,
                "avg_latency_ms": 0.0,
                "p50_latency_ms": 0.0,
                "p95_latency_ms": 0.0,
                "max_latency_ms": 0.0,
                "total_network_sec": 0.0,
                "concurrency_overlap": 1.0,
                "total_payload_kb": 0.0,
                "avg_payload_kb": 0.0,
                "failed_requests": 0,
            }

        sorted_lat = sorted(self.latencies_ms)
        n = len(sorted_lat)
        total_net_sec = sum(sorted_lat) / 1000.0
        overlap = round(total_net_sec / max(wall_clock_sec, 0.001), 2) if wall_clock_sec > 0 else 1.0
        total_kb = sum(self.payload_bytes) / 1024.0

        return {
            "request_count": n,
            "avg_latency_ms": round(sum(sorted_lat) / n, 2),
            "p50_latency_ms": round(sorted_lat[int(n * 0.50)], 2),
            "p95_latency_ms": round(sorted_lat[min(int(n * 0.95), n - 1)], 2),
            "max_latency_ms": round(sorted_lat[-1], 2),
            "total_network_sec": round(total_net_sec, 3),
            "concurrency_overlap": overlap,
            "total_payload_kb": round(total_kb, 1),
            "avg_payload_kb": round(total_kb / n, 1),
            "failed_requests": self.failed_requests,
        }


@contextmanager
def track_api_calls():
    """Transparently records all requests and httpx outbound HTTP calls."""
    stats = APILatencyStats()
    orig_req_send = requests.Session.send
    orig_http_send = httpx.AsyncClient.send

    def patched_req_send(self, request, **kwargs):
        t0 = time.perf_counter()
        resp = orig_req_send(self, request, **kwargs)
        duration = time.perf_counter() - t0
        content_len = len(resp.content) if hasattr(resp, "_content") and resp._content is not None else 0
        stats.record(duration, content_len, resp.status_code)
        return resp

    async def patched_http_send(self, request, **kwargs):
        t0 = time.perf_counter()
        resp = await orig_http_send(self, request, **kwargs)
        duration = time.perf_counter() - t0
        content_len = len(resp.content) if hasattr(resp, "_content") and resp._content is not None else 0
        stats.record(duration, content_len, resp.status_code)
        return resp

    requests.Session.send = patched_req_send
    httpx.AsyncClient.send = patched_http_send
    try:
        yield stats
    finally:
        requests.Session.send = orig_req_send
        httpx.AsyncClient.send = orig_http_send


def get_git_commit() -> str:
    """Returns the current short git commit hash, or 'uncommitted' on failure."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        )
        return res.stdout.strip()
    except Exception:
        return "uncommitted"


def get_run_timestamp() -> Tuple[str, str]:
    """Returns a tuple of (ISO 8601 string, compact file tag string)."""
    now = datetime.now(timezone.utc)
    return now.isoformat(), now.strftime("%Y%m%d_%H%M%S")


def save_benchmark_artifacts(
    df: pd.DataFrame,
    fig,
    name_prefix: str,
    results_dir: str = "evaluation/results",
    file_tag: str = None,
    trials_df: pd.DataFrame = None,
    **kwargs,
) -> Tuple[str, str]:
    """
    Saves benchmark CSV results, PNG plots, and trial run CSVs into a timestamped directory:
    <results_dir>/<file_tag>/<name_prefix>.csv
    <results_dir>/<file_tag>/<name_prefix>.png
    <results_dir>/<file_tag>/trials/<subname>/trial_<N>.csv
    <results_dir>/<file_tag>/trials/<subname>/all_trials.csv
    Returns (csv_path, png_path).
    """
    if file_tag is None:
        _, file_tag = get_run_timestamp()

    run_dir = os.path.join(results_dir, file_tag)
    os.makedirs(run_dir, exist_ok=True)

    csv_path = os.path.join(run_dir, f"{name_prefix}.csv")
    png_path = os.path.join(run_dir, f"{name_prefix}.png")

    df.to_csv(csv_path, index=False)
    fig.savefig(png_path, dpi=300)

    if trials_df is not None and not trials_df.empty:
        subname = "synthetic" if ("synthetic" in name_prefix or "dummy" in name_prefix) else ("live" if "live" in name_prefix else "")
        trials_dir = os.path.join(run_dir, "trials", subname) if subname else os.path.join(run_dir, "trials")
        os.makedirs(trials_dir, exist_ok=True)
        trials_df.to_csv(os.path.join(trials_dir, "all_trials.csv"), index=False)
        if "trial" in trials_df.columns:
            for t_val, t_grp in trials_df.groupby("trial"):
                t_grp.to_csv(os.path.join(trials_dir, f"trial_{t_val}.csv"), index=False)

    return csv_path, png_path
