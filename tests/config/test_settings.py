from pathlib import Path

import pytest

from reverseai.config import load_settings


def test_default_settings_load():
    s = load_settings()
    assert s.roles["executor"].candidates[0] == "claude-sonnet-5-5"
    assert s.providers["deepseek"].jurisdiction == "cn"
    assert s.models["claude-opus-5-5"].output_per_mtok == 20


def _write_variant(tmp_path: Path, old: str, new: str) -> Path:
    from reverseai.config import DEFAULT_CONFIG_PATH

    text = DEFAULT_CONFIG_PATH.read_text(encoding="utf-8")
    assert old in text
    p = tmp_path / "settings.yaml"
    p.write_text(text.replace(old, new, 1), encoding="utf-8")
    return p


def test_unknown_candidate_rejected(tmp_path):
    p = _write_variant(
        tmp_path,
        "candidates: [claude-sonnet-5-5, gpt-6.1-sol, deepseek-v4-pro, glm-5.3]",
        "candidates: [nope]",
    )
    with pytest.raises(ValueError, match="nope"):
        load_settings(p)


def test_unknown_provider_rejected(tmp_path):
    p = _write_variant(tmp_path, "provider: zai", "provider: ghost")
    with pytest.raises(ValueError, match="ghost"):
        load_settings(p)


def test_defaults_and_cached_price():
    s = load_settings()
    assert s.roles["planner"].max_output_tokens == 8192
    assert s.models["deepseek-v4-pro"].cached_input_per_mtok == 0.044
    assert s.roles["bulk"].candidates[0] == "claude-haiku-5-5"


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("    api_key_env: ZAI_API_KEY\n", "    api_key_env: ZAI_API_KEY\n    api_key: inline\n"),
        ("    output_per_mtok: 4.40\n", "    output_per_mtok: 4.40\n    output_per_mtk: 1\n"),
        ("  bulk:\n", "  bulk:\n    max_output_token: 10\n"),
        ("providers:\n", "provider_defaults: {}\nproviders:\n"),
    ],
)
def test_unknown_keys_are_rejected(tmp_path, old, new):
    with pytest.raises(ValueError, match="xtra"):
        load_settings(_write_variant(tmp_path, old, new))


def test_a_role_needs_at_least_one_candidate(tmp_path):
    p = _write_variant(
        tmp_path,
        "candidates: [claude-haiku-5-5, gpt-6-luna, deepseek-v4.1-flash]",
        "candidates: []",
    )
    with pytest.raises(ValueError, match="candidates"):
        load_settings(p)
