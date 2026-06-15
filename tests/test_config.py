"""Tests for garmin.config credential loading."""

import pytest

from garmin.config import Config, Credentials, _parse_env_file, load_config

_RECOGNISED_KEYS = (
    "GARMIN_CN_EMAIL",
    "GARMIN_CN_PASSWORD",
    "GARMIN_GLOBAL_EMAIL",
    "GARMIN_GLOBAL_PASSWORD",
    "username",
    "password",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Remove recognised credential keys so tests are deterministic."""
    for key in _RECOGNISED_KEYS:
        monkeypatch.delenv(key, raising=False)


def _write_env(tmp_path, body: str):
    path = tmp_path / "env"
    path.write_text(body)
    return path


def test_parse_env_file_ignores_comments_and_blanks(tmp_path):
    path = _write_env(
        tmp_path,
        "# comment\n"
        "\n"
        "GARMIN_CN_EMAIL=a@x.com\n"
        "  GARMIN_CN_PASSWORD = secret \n"
        "bad line\n",
    )
    values = _parse_env_file(path)
    assert values == {"GARMIN_CN_EMAIL": "a@x.com", "GARMIN_CN_PASSWORD": "secret"}


def test_parse_env_file_missing_returns_empty(tmp_path):
    assert _parse_env_file(tmp_path / "does-not-exist") == {}


def test_load_config_from_env_file(tmp_path):
    path = _write_env(
        tmp_path,
        "GARMIN_CN_EMAIL=cn@x.com\nGARMIN_CN_PASSWORD=cnpw\n"
        "GARMIN_GLOBAL_EMAIL=g@x.com\nGARMIN_GLOBAL_PASSWORD=gpw\n",
    )
    config = load_config(env_path=path)
    assert config.cn == Credentials("cn@x.com", "cnpw")
    assert config.global_ == Credentials("g@x.com", "gpw")


def test_env_var_takes_precedence_over_file(tmp_path, monkeypatch):
    path = _write_env(
        tmp_path, "GARMIN_CN_EMAIL=file@x.com\nGARMIN_CN_PASSWORD=filepw\n"
    )
    monkeypatch.setenv("GARMIN_CN_EMAIL", "env@x.com")
    config = load_config(env_path=path)
    assert config.cn.email == "env@x.com"
    assert config.cn.password == "filepw"


def test_legacy_username_password_aliases(tmp_path):
    path = _write_env(tmp_path, "username=legacy@x.com\npassword=legacypw\n")
    config = load_config(env_path=path)
    assert config.cn == Credentials("legacy@x.com", "legacypw")
    assert config.global_ is None


def test_missing_cn_credentials_raises(tmp_path):
    with pytest.raises(RuntimeError, match="Garmin CN credentials"):
        load_config(env_path=tmp_path / "missing-env")


def test_require_global_raises_when_absent():
    config = Config(cn=Credentials("a", "b"), global_=None)
    with pytest.raises(RuntimeError, match="Garmin Global credentials"):
        config.require_global()


def test_require_global_returns_when_present():
    creds = Credentials("g@x.com", "pw")
    config = Config(cn=Credentials("a", "b"), global_=creds)
    assert config.require_global() is creds
