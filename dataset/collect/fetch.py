"""Polite HTTP fetcher: robots.txt check, 1 request/second per host, local cache, back-off on 429."""
import hashlib
import re
import time
from pathlib import Path
from urllib.parse import urlsplit

import requests

USER_AGENT = "Mozilla/5.0 (compatible; ProductLens-research/0.1; shirt product dataset research)"
CACHE = Path(__file__).resolve().parents[1] / ".cache"
MIN_INTERVAL = 1.0  # seconds between requests to one host


class Blocked(Exception):
    """The URL is disallowed by robots.txt or the server refused us (challenge page, repeated 429)."""


def robots_allows(robots_txt, path, agent="productlens"):
    """Minimal robots.txt matcher with * and $ wildcards; longest matching rule wins (RFC 9309)."""
    groups, current, seen_rule = [], None, False
    for line in robots_txt.splitlines():
        line = line.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        key, value = (s.strip() for s in line.split(":", 1))
        key = key.lower()
        if key == "user-agent":
            if current is None or seen_rule:
                current, seen_rule = {"agents": [], "rules": []}, False
                groups.append(current)
            current["agents"].append(value.lower())
        elif key in ("allow", "disallow") and current is not None:
            seen_rule = True
            if value:
                current["rules"].append((key == "allow", value))
    mine = [g for g in groups if any(a != "*" and a in agent for a in g["agents"])]
    rules = [r for g in (mine or [g for g in groups if "*" in g["agents"]]) for r in g["rules"]]
    best = (-1, True)
    for allow, pattern in rules:
        regex = "".join(".*" if c == "*" else "$" if c == "$" and i == len(pattern) - 1 else re.escape(c)
                        for i, c in enumerate(pattern))
        if re.match(regex, path) and (len(pattern) > best[0] or (len(pattern) == best[0] and allow)):
            best = (len(pattern), allow)
    return best[1]


class Fetcher:
    def __init__(self, use_cache=True):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept": "text/html,application/json;q=0.9,*/*;q=0.8"})
        self.last = {}
        self.robots = {}
        self.use_cache = use_cache
        CACHE.mkdir(parents=True, exist_ok=True)

    def _wait(self, host):
        delay = self.last.get(host, 0) + MIN_INTERVAL - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        self.last[host] = time.monotonic()

    def _robots(self, scheme, host):
        if host not in self.robots:
            self._wait(host)
            r = self.session.get(f"{scheme}://{host}/robots.txt", timeout=30)
            self.robots[host] = r.text if r.status_code == 200 else ""
        return self.robots[host]

    def get(self, url):
        """Return (final_url, text). Raises Blocked when robots.txt disallows or the server refuses."""
        parts = urlsplit(url)
        path = parts.path + (f"?{parts.query}" if parts.query else "")
        if not robots_allows(self._robots(parts.scheme, parts.netloc), path):
            raise Blocked(f"robots.txt disallows {url}")
        key = CACHE / (hashlib.sha256(url.encode()).hexdigest()[:24] + ".txt")
        if self.use_cache and key.exists():
            final, _, text = key.read_text(encoding="utf-8").partition("\n")
            return final, text
        for attempt in range(3):
            self._wait(parts.netloc)
            r = self.session.get(url, timeout=30)
            challenged = "connection needs to be verified" in r.text[:5000].lower()
            if r.status_code == 200 and not challenged:
                key.write_text(r.url + "\n" + r.text, encoding="utf-8")
                return r.url, r.text
            if r.status_code in (429, 503) or challenged:
                time.sleep(min(int(r.headers.get("Retry-After", "0") or 0) or 30 * (attempt + 1), 120))
                continue
            raise Blocked(f"HTTP {r.status_code} for {url}")
        raise Blocked(f"refused (429/challenge) for {url}")
