"""In-process brute-force throttle for password sign-in (single-instance factory-console).

Per-key (email AND client IP) failed-attempt counter with exponential backoff. The caller checks
`retry_after()` BEFORE the scrypt verify, so a throttled attempt costs nothing — closing both online
brute-force AND the scrypt-per-attempt DoS in one place. Counters are in-memory with idle-TTL
eviction; correct for ONE replica. If factory-console ever scales to multiple replicas this must move
to a shared store (Redis/PG) — flagged, not built now.

Two keys are recorded per attempt: the (lowercased) email and the client IP. A spray across many
emails from one IP still trips the IP key; repeated hits on one email from rotating IPs still trip
the email key. The effective wait is the MAX across the attempt's keys.
"""
import threading
import time


class LoginThrottle:
    def __init__(self, free_email=5, free_ip=10, base=2.0, cap=900.0, window=900.0):
        # free_*: failed attempts allowed before the first lock. email (5) is the tight per-account net;
        # ip (10) is looser — it shares one IP across a NAT/office, and must stay above free_email so a
        # single user hitting their own email limit doesn't prematurely trip the IP net — but tight
        # enough to bound a single-source spray across many accounts. base/cap: exp backoff sec, clamped.
        # window: idle TTL — a key with no failure for this long is forgotten (counter resets to 0).
        self.free = {"email": free_email, "ip": free_ip}
        self.base, self.cap, self.window = base, cap, window
        self._fails: dict[str, list] = {}   # key -> [count, locked_until, last_seen]
        self._lock = threading.Lock()

    def _free_for(self, key: str) -> int:
        return self.free["email"] if key.startswith("email:") else self.free["ip"]

    def _evict(self, now: float):
        for k in [k for k, e in self._fails.items() if now - e[2] > self.window]:
            del self._fails[k]

    def retry_after(self, keys, now=None) -> int:
        """Seconds the caller must wait before this attempt is allowed (max across keys); 0 = allowed."""
        now = time.time() if now is None else now
        wait = 0.0
        with self._lock:
            for k in keys:
                e = self._fails.get(k)
                if e and e[1] > now and now - e[2] <= self.window:
                    wait = max(wait, e[1] - now)
        from math import ceil
        return ceil(wait) if wait > 0 else 0

    def record_failure(self, keys, now=None):
        """Count a failed attempt against every key and (re)arm the backoff lock once past the free tier."""
        now = time.time() if now is None else now
        with self._lock:
            self._evict(now)
            for k in keys:
                e = self._fails.get(k)
                if e is None or now - e[2] > self.window:
                    e = [0, 0.0, now]            # fresh / expired → reset counter
                e[0] += 1
                e[2] = now
                free = self._free_for(k)
                if e[0] > free:
                    backoff = min(self.base * (2 ** (e[0] - free - 1)), self.cap)
                    e[1] = now + backoff
                self._fails[k] = e

    def reset(self, keys):
        """Clear counters for these keys — called on a successful login so a good user starts clean."""
        with self._lock:
            for k in keys:
                self._fails.pop(k, None)
