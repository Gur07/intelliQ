"""
core/rate_limiter.py
Sliding-window rate limiter (4 calls/min) and per-call tracker.
llm_call() wraps every LLM invocation — import it in nodes.py.
"""

import time
import threading
from collections import deque
from datetime import datetime
from typing import Dict, List


class RateLimiter:
    def __init__(self, max_calls: int = 4, window_sec: int = 60):
        self.max_calls  = max_calls
        self.window_sec = window_sec
        self._ts: deque = deque()
        self._lock      = threading.Lock()

    def acquire(self, label: str = ""):
        while True:
            with self._lock:
                now = time.time()
                while self._ts and now - self._ts[0] >= self.window_sec:
                    self._ts.popleft()
                if len(self._ts) < self.max_calls:
                    self._ts.append(now)
                    return
                wait = self.window_sec - (now - self._ts[0]) + 0.1
            print(
                f"  [rate-limit] {label} — {len(self._ts)}/{self.max_calls} used, "
                f"waiting {wait:.1f}s ...",
                flush=True,
            )
            time.sleep(wait)


class CallTracker:
    def __init__(self):
        self._calls: List[Dict] = []
        self._lock = threading.Lock()

    def record(self, node: str, status: str, latency_ms: int, detail: str = ""):
        entry = dict(
            seq=len(self._calls) + 1,
            time=datetime.now().strftime("%H:%M:%S"),
            node=node, status=status,
            latency_ms=latency_ms, detail=detail,
        )
        with self._lock:
            self._calls.append(entry)

    def get_calls(self) -> List[Dict]:
        with self._lock:
            return list(self._calls)

    def reset(self):
        with self._lock:
            self._calls.clear()

    def summary(self) -> Dict:
        calls = self.get_calls()
        n = len(calls)
        return {
            "total":    n,
            "ok":       sum(1 for c in calls if c["status"] == "ok"),
            "cached":   sum(1 for c in calls if c["status"] == "cache"),
            "errors":   sum(1 for c in calls if c["status"] == "error"),
            "avg_ms":   sum(c["latency_ms"] for c in calls) // n if n else 0,
        }


# Module-level singletons — imported by nodes.py
rate_limiter = RateLimiter(max_calls=4, window_sec=60)
tracker      = CallTracker()


def llm_call(node: str, chain, messages: list):
    """Rate-limit + track every LLM call. Raise on error (caller handles it)."""
    rate_limiter.acquire(label=node)
    t0 = time.time()
    try:
        result = chain.invoke(messages)
        tracker.record(node, "ok", int((time.time() - t0) * 1000))
        return result
    except Exception as e:
        tracker.record(node, "error", int((time.time() - t0) * 1000), str(e)[:80])
        raise
