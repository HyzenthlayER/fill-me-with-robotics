"""M08: evidence-based issues and bounded interpretations."""

from dataclasses import asdict, dataclass, field


@dataclass
class Issue:
    code: str
    message: str
    time_interval_s: tuple[float, float] = (0.0, 0.0)
    severity: str = "error"
    measured: float | None = None
    limit: float | None = None
    unit: str = ""
    source: str = "planning"
    scope: str = "sampled candidate"
    entity_ids: list[str] = field(default_factory=list)
    suggestion: str = ""

    def to_dict(self):
        return asdict(self)


def coalesce(issues):
    """Join consecutive equal diagnostics, retaining the worst measured value."""
    result = []
    for issue in issues:
        if result:
            previous = result[-1]
            key = lambda i: (i.code, i.source, i.scope, i.unit, i.limit, i.entity_ids)
            if (
                key(issue) == key(previous)
                and issue.time_interval_s[0] - previous.time_interval_s[1] <= 0.011
            ):
                previous.time_interval_s = (
                    previous.time_interval_s[0],
                    issue.time_interval_s[1],
                )
                if issue.measured is not None:
                    previous.measured = max(previous.measured or 0, issue.measured)
                continue
        result.append(Issue(**issue.to_dict()))
    return result


def solver_issue(status, time_s, message=""):
    codes = {
        "timeout": "SOLVER_TIMEOUT",
        "cancelled": "CANCELLED",
        "numerical_error": "SOLVER_NUMERICAL_ERROR",
        "fixed_pose_infeasible": "STATIC_BALANCE",
        "no_solution_found": "NO_SOLUTION_FOUND",
    }
    return Issue(
        codes.get(status, "SOLVER_ERROR"),
        message or status,
        (time_s, time_s),
        scope="this solve; no claim of global infeasibility",
    )
