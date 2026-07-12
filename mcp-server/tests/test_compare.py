from mcp_server import queries


def test_compare_builds_matrix_and_reports_missing(monkeypatch) -> None:
    fake = {
        "alpha-travel": {
            "slug": "alpha-travel",
            "insurer_name": "Alpha",
            "summary": "Basic travel",
            "currency": "PHP",
            "premium_min": 500,
            "coverage": {"line": "travel"},
        },
        "beta-travel": {
            "slug": "beta-travel",
            "insurer_name": "Beta",
            "summary": "Premium travel",
            "currency": "PHP",
            "premium_min": 900,
            "coverage": {"line": "travel"},
        },
    }
    monkeypatch.setattr(queries, "get_policy", lambda slug: fake.get(slug))

    result = queries.compare_policies(["alpha-travel", "beta-travel", "ghost"])

    assert result["policies"] == ["alpha-travel", "beta-travel"]
    assert result["not_found"] == ["ghost"]
    assert result["comparison"]["premium_min"] == {"alpha-travel": 500, "beta-travel": 900}
    # every compare field present for every found policy
    for field in queries.COMPARE_FIELDS:
        assert set(result["comparison"][field].keys()) == {"alpha-travel", "beta-travel"}
