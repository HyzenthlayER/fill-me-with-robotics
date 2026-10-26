from contact_composer.diagnostics import Issue, coalesce, solver_issue


def test_adjacent_issues_keep_evidence_and_do_not_cross_sources():
    issues = [
        Issue("DRIFT", "drift", (0, 0.01), measured=0.03, limit=0.02, unit="m"),
        Issue("DRIFT", "drift", (0.01, 0.02), measured=0.04, limit=0.02, unit="m"),
        Issue(
            "DRIFT",
            "drift",
            (0.02, 0.03),
            measured=0.05,
            limit=0.02,
            unit="m",
            source="simulation",
        ),
    ]
    merged = coalesce(issues)
    assert len(merged) == 2
    assert merged[0].time_interval_s == (0, 0.02)
    assert merged[0].measured == 0.04
    assert issues[0].time_interval_s == (0, 0.01)


def test_timeout_does_not_claim_infeasibility():
    issue = solver_issue("timeout", 2.5)
    assert issue.code == "SOLVER_TIMEOUT"
    assert issue.measured is None
    assert "no claim of global infeasibility" in issue.scope
