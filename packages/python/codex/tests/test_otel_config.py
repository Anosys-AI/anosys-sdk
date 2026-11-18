"""Codex OTel export (--otel-key): never break config.toml, never touch a user's own [otel]."""

import pytest

try:
    import tomllib
except ImportError:  # Python 3.10
    import tomli as tomllib

from anosys_sdk_codex.installer import OtelConfigError, has_anosys_otel, remove_codex_otel, update_codex_otel

ORIGINAL = '''model = "gpt-5"
notify = ["/usr/local/bin/other-notifier", "turn-ended"]

[projects."/tmp/repo"]
trust_level = "trusted"

[tui.model_availability_nux]
gpt-6 = 4
'''


def _config(tmp_path, content=ORIGINAL):
    path = tmp_path / "config.toml"
    path.write_text(content, encoding="utf-8")
    return path


def test_writes_valid_otel_block_with_prompts_off(tmp_path):
    path = _config(tmp_path)
    assert update_codex_otel("otel-key-1", path=path) is True
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    assert data["otel"]["log_user_prompt"] is False
    for field, signal in (("exporter", "logs"), ("trace_exporter", "traces"), ("metrics_exporter", "metrics")):
        assert data["otel"][field] == {"otlp-http": {
            "endpoint": f"https://api.anosys.ai/ingestion/v1/{signal}", "protocol": "binary",
            "headers": {"anosys-apikey": "otel-key-1"}}}
    assert data["notify"] == ["/usr/local/bin/other-notifier", "turn-ended"]
    assert data["projects"]["/tmp/repo"]["trust_level"] == "trusted"
    assert has_anosys_otel(path)


def test_rerun_idempotent_and_key_replaced(tmp_path):
    path = _config(tmp_path)
    update_codex_otel("k1", path=path)
    assert update_codex_otel("k1", path=path) is False
    assert update_codex_otel("k2", path=path) is True
    text = path.read_text(encoding="utf-8")
    assert text.count("\n[otel]\n") == 1
    assert tomllib.loads(text)["otel"]["exporter"]["otlp-http"]["headers"]["anosys-apikey"] == "k2"


def test_uninstall_restores_byte_for_byte(tmp_path):
    path = _config(tmp_path)
    update_codex_otel("k1", path=path)
    assert remove_codex_otel(path=path) is True
    assert path.read_text(encoding="utf-8") == ORIGINAL
    assert remove_codex_otel(path=path) is False


def test_user_owned_otel_is_never_touched(tmp_path):
    content = ORIGINAL + '\n[otel]\nenvironment = "prod"\n'
    path = _config(tmp_path, content)
    with pytest.raises(OtelConfigError):
        update_codex_otel("k1", path=path)
    assert path.read_text(encoding="utf-8") == content


def test_invalid_config_left_alone(tmp_path):
    content = 'notify = ["a"\nbroken'
    path = _config(tmp_path, content)
    with pytest.raises(OtelConfigError):
        update_codex_otel("k1", path=path)
    assert path.read_text(encoding="utf-8") == content


def test_key_is_escaped(tmp_path):
    path = _config(tmp_path)
    update_codex_otel('a"b\\c', path=path)
    assert tomllib.loads(path.read_text(encoding="utf-8"))["otel"]["exporter"]["otlp-http"]["headers"]["anosys-apikey"] == 'a"b\\c'


def test_empty_config(tmp_path):
    path = _config(tmp_path, "")
    assert update_codex_otel("k1", path=path) is True
    assert tomllib.loads(path.read_text(encoding="utf-8"))["otel"]["log_user_prompt"] is False
