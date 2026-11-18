"""Failure injection — the real point of a mock.

"The point of the mock is to reproduce failure modes, not just happy paths"
(insights360 spec, §4.1). The original mock could only simulate one failure: a
collection added to a Python `set`, so only from the same process. As soon as
the mock runs in a container — which is the case for insights360, in compose
as in a Tekton sidecar — that path disappears.

Hence: declarative injection rules, controllable over HTTP (`/__admin`).

A SINGLE dispatch point, ordered, evaluated BEFORE authentication, so that
`auth_reject` can preempt it. Every rule carries an optional `times` counter: a
"transient" failure must stop on its own, otherwise we are not testing a
retry, we are testing a failure.
"""

from __future__ import annotations

import fnmatch
import time
from dataclasses import dataclass, field
from typing import Any, Literal, get_args

Kind = Literal[
    "rate_limit",
    "status",
    "latency",
    "page_drift",
    "auth_reject",
    "unstable_order",
    "page_cap",
    "maxresults_cap",
    "ignore_period",
]

#: Every kind `/__admin/inject` accepts — derived from `Kind`, so the two
#: cannot drift apart.
KINDS: tuple[str, ...] = get_args(Kind)


@dataclass
class Rule:
    """An injection rule.

    `scope` is a glob pattern on the path (`/api/resources`, `/api/*`, `*`),
    which lets a precise collection be targeted without enumerating its
    routes.
    """

    id: str
    kind: Kind
    scope: str = "*"
    # Number of remaining applications. None = unlimited. Decremented on each
    # trigger: that is what makes the difference between a transient failure
    # (that a retry should absorb) and a persistent failure (that must make
    # the run fail with a non-zero exit code).
    times: int | None = None

    # rate_limit, and status since 0.12.0: the rule fires only once the path
    # has been requested MORE than `after_requests` times. "The third call
    # fails" is how a failure in the middle of a walk is written.
    after_requests: int = 0
    retry_after_seconds: int = 1
    # status
    status: int = 500
    # latency
    seconds: float = 0.0
    # page_drift, page_cap
    after_page: int = 1
    mode: Literal["insert", "remove"] = "insert"
    # maxresults_cap: a `maxResults` above `limit` falls back to the default
    # page size, as the vendor does above its own cap.
    limit: int | None = None

    extra: dict[str, Any] = field(default_factory=dict)

    def matches(self, path: str) -> bool:
        return fnmatch.fnmatch(path, self.scope)

    def consume(self) -> bool:
        """Decrements the counter. Returns False once the rule is exhausted."""
        if self.times is None:
            return True
        if self.times <= 0:
            return False
        self.times -= 1
        return True


#: Calls kept per path in the control plane's history.
_HISTORY_MAX = 500


class InjectionEngine:
    """The engine, and the per-path request counter it depends on."""

    def __init__(self) -> None:
        self.rules: list[Rule] = []
        self.request_counts: dict[str, int] = {}
        self.last_query_params: dict[str, dict[str, str]] = {}
        # The HISTORY, not just the last call: two legitimate consumers can
        # hit the same path with different strategies (resources in
        # incremental, contracts in full refresh). Keeping only the last one
        # makes the control plane lie — observed on 2026-08-13: a consumer-side
        # incrementality test failed because the second caller overwrote the
        # first one's trace. Bounded per path: unbounded growth would
        # eventually get truncated anyway.
        self.query_params_history: dict[str, list[dict[str, str]]] = {}
        # Every request under /api, routed or not, and the refused methods
        # (405) among them. What a consumer compares with its own call ledger:
        # a client that believes it sent 2 calls while the mock saw 3 has a
        # retry it does not count, and its daily budget is wrong.
        self.total_requests = 0
        self.refused_methods = 0
        self._next_id = 1
        # Virtual clock: lets time windows be tested without `sleep`, so
        # without making the suite slow or dependent on real timing.
        self.clock_offset: float = 0.0

    # ── Rule management ──────────────────────────────────────────────────────

    def add(self, **kwargs: Any) -> Rule:
        rule = Rule(id=f"r{self._next_id}", **kwargs)
        self._next_id += 1
        self.rules.append(rule)
        return rule

    def remove(self, rule_id: str) -> bool:
        before = len(self.rules)
        self.rules = [r for r in self.rules if r.id != rule_id]
        return len(self.rules) != before

    def clear(self) -> None:
        self.rules.clear()

    def reset_counters(self) -> None:
        self.request_counts.clear()
        self.last_query_params.clear()
        self.query_params_history.clear()
        self.total_requests = 0
        self.refused_methods = 0
        self.clock_offset = 0.0

    # ── Observation ──────────────────────────────────────────────────────────

    def observe(self, path: str, params: dict[str, str]) -> int:
        """Records a request's passage and returns its rank (1-based).

        `last_query_params` is load-bearing: it is what lets a consumer prove
        it actually SENT the incremental parameter and the sort order, instead
        of merely tolerating their absence. A pipeline that forgot its cursor
        would otherwise pass all its tests.
        """
        self.total_requests += 1
        self.request_counts[path] = self.request_counts.get(path, 0) + 1
        self.last_query_params[path] = dict(params)
        history = self.query_params_history.setdefault(path, [])
        history.append(dict(params))
        if len(history) > _HISTORY_MAX:
            del history[0]
        return self.request_counts[path]

    def observe_unrouted(self, path: str, status: int) -> None:
        """Counts a request that never reached a route: unknown path or method.

        Only under /api: `/health` and `/__admin` are not calls to the vendor.
        A refused method stays visible on its own, because the only methods a
        read-only consumer may send are GETs — one 405 is already a bug.
        """
        if not path.startswith("/api"):
            return
        self.total_requests += 1
        if status == 405:
            self.refused_methods += 1

    def now(self) -> float:
        return time.time() + self.clock_offset

    # ── Dispatch ─────────────────────────────────────────────────────────────

    def first(self, kind: Kind, path: str) -> Rule | None:
        """First active rule of the requested kind for this path."""
        for rule in self.rules:
            if rule.kind == kind and rule.matches(path):
                if rule.times is not None and rule.times <= 0:
                    continue
                return rule
        return None

    def snapshot(self) -> list[dict[str, Any]]:
        return [
            {
                "id": r.id,
                "kind": r.kind,
                "scope": r.scope,
                "times_left": r.times,
                **{
                    k: v
                    for k, v in (
                        ("after_requests", r.after_requests),
                        ("retry_after_seconds", r.retry_after_seconds),
                        ("status", r.status),
                        ("seconds", r.seconds),
                        ("after_page", r.after_page),
                        ("mode", r.mode),
                        ("limit", r.limit),
                    )
                    if _relevant(r.kind, k)
                },
            }
            for r in self.rules
        ]


_FIELDS_BY_KIND: dict[str, set[str]] = {
    "rate_limit": {"after_requests", "retry_after_seconds"},
    "status": {"status", "after_requests"},
    "latency": {"seconds"},
    "page_drift": {"after_page", "mode"},
    "auth_reject": {"status"},
    "unstable_order": set(),
    "page_cap": {"after_page"},
    "maxresults_cap": {"limit"},
    "ignore_period": set(),
}


def _relevant(kind: str, field_name: str) -> bool:
    return field_name in _FIELDS_BY_KIND.get(kind, set())


def allowed_options(kind: str) -> set[str]:
    """The keys an `/__admin/inject` body may carry for this kind."""
    return {"scope", "times"} | _FIELDS_BY_KIND.get(kind, set())


engine = InjectionEngine()
