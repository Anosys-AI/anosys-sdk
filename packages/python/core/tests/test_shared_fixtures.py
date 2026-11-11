"""
Golden cases shared with the JS core tests (packages/fixtures). The same JSON drives
both suites, so Python and JS cannot drift on levels, filtering, labels or mapping.
"""

import json
from pathlib import Path

import pytest

from anosys_sdk_core import models
from anosys_sdk_core.capture import app_consent_value, finalize_app_record, resolve_app_level
from anosys_sdk_core.privacy import BASE_METADATA_FIELDS, POLICY_VERSION, consent_value, effective_level, filter_fields
from anosys_sdk_core.util.batching import assign

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures"
CASES = json.loads((FIXTURES / "privacy_cases.json").read_text())
MAPPINGS = json.loads((FIXTURES / "mappings.json").read_text())
ENV_VARS = ("ANOSYS_DISABLE", "ANOSYS_COLLECTION_LEVEL", "REDACTION")


@pytest.fixture
def world(monkeypatch, tmp_path):
    for var in ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("ANOSYS_CONSENT_FILE", str(tmp_path / "consent.json"))
    monkeypatch.chdir(tmp_path)

    def setup(case):
        for k, v in case.get("env", {}).items():
            monkeypatch.setenv(k, v)
        if case.get("project"):
            (tmp_path / ".anosys").write_text(f"level={case['project']}\n")
        if case.get("consent"):
            version = POLICY_VERSION if case["consent"] == "current" else "2000-01-01"
            (tmp_path / "consent.json").write_text(json.dumps({"level": "full", "policy_version": version}))
    return setup


@pytest.mark.parametrize("case", CASES["app_level"])
def test_app_level(world, case):
    world(case)
    assert list(resolve_app_level(case["explicit"])) == case["expected"]


@pytest.mark.parametrize("case", CASES["hook_level"])
def test_hook_level(world, case):
    world(case)
    assert list(effective_level(case["explicit"])) == case["expected"]


@pytest.mark.parametrize("case", CASES["app_finalize"])
def test_app_finalize(case):
    assert finalize_app_record(case["record"], case["level"], case["extra"]) == case["expected"]


@pytest.mark.parametrize("case", CASES["hook_filter"])
def test_hook_filter(case):
    assert filter_fields(case["record"], case["level"], BASE_METADATA_FIELDS) == case["expected"]


def test_consent_values():
    v = CASES["consent_values"]
    assert consent_value("full") == v["full"] == f"full;{POLICY_VERSION}"
    assert consent_value("metadata") == v["metadata"] and consent_value("off") == v["off"]
    assert app_consent_value("full") == v["app_full"] and app_consent_value("metadata") == v["app_metadata"]


@pytest.mark.parametrize("case", CASES["assign"])
def test_assign(case):
    out = {}
    assign(out, "k", case["value"])
    value = json.loads(out["k"]) if case.get("json") else out["k"]
    assert value == case["expected"]


def test_python_tables_equal_the_shared_fixture():
    agents = pytest.importorskip("anosys_sdk_openai_agents.mapping")
    for name in ("BASE_KEY_MAPPING", "CLAUDE_KEY_MAPPING", "OTEL_AI_VALID_TYPES", "CLAUDE_VALID_TYPES",
                 "DEFAULT_STARTING_INDICES", "CLAUDE_STARTING_INDICES"):
        assert getattr(models, name) == MAPPINGS[name], name
    assert agents.AGENTS_KEY_MAPPING == MAPPINGS["AGENTS_KEY_MAPPING"]
