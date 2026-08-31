import json

import pytest

from pa import auth, config
from pa.errors import AuthError

GMAIL = auth.SCOPES["gmail"]


def test_covers_exact_and_superset():
    assert auth._covers(" ".join(GMAIL), GMAIL)
    assert auth._covers(GMAIL, GMAIL)
    # mail.google.com is Gmail's superset scope and must satisfy any gmail scope.
    assert auth._covers("https://mail.google.com/", GMAIL)


def test_covers_rejects_partial_and_empty():
    assert not auth._covers(GMAIL[:1], GMAIL)
    assert not auth._covers("", GMAIL)
    assert not auth._covers(None, GMAIL)
    assert not auth._covers("https://www.googleapis.com/auth/calendar", GMAIL)


def write_legacy(directory, scope, refresh="rt-legacy"):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "gcp-oauth.keys.json").write_text(json.dumps({"installed": {
        "client_id": "cid", "client_secret": "secret",
        "token_uri": "https://oauth2.googleapis.com/token",
    }}))
    (directory / "credentials.json").write_text(json.dumps({
        "access_token": "at", "refresh_token": refresh, "scope": scope,
    }))


def test_describe_source_reports_none_when_nothing_configured():
    assert auth.describe_source("gmail") == "none"
    assert auth.describe_source("contacts") == "none"


def test_legacy_mcp_credentials_are_discovered(tmp_path, monkeypatch):
    legacy = tmp_path / "gmail-mcp"
    write_legacy(legacy, " ".join(GMAIL))
    monkeypatch.setitem(config.LEGACY_MCP_DIRS, "gmail", legacy)
    assert "legacy MCP" in auth.describe_source("gmail")


def test_legacy_credentials_ignored_when_scopes_insufficient(tmp_path, monkeypatch):
    legacy = tmp_path / "gmail-mcp"
    write_legacy(legacy, "https://www.googleapis.com/auth/gmail.readonly")
    monkeypatch.setitem(config.LEGACY_MCP_DIRS, "gmail", legacy)
    assert auth.describe_source("gmail") == "none"


def test_legacy_credentials_ignored_without_refresh_token(tmp_path, monkeypatch):
    legacy = tmp_path / "gmail-mcp"
    write_legacy(legacy, " ".join(GMAIL), refresh="")
    monkeypatch.setitem(config.LEGACY_MCP_DIRS, "gmail", legacy)
    assert auth.describe_source("gmail") == "none"


def test_legacy_fallback_is_only_for_the_default_account(tmp_path, monkeypatch):
    legacy = tmp_path / "gmail-mcp"
    write_legacy(legacy, " ".join(GMAIL))
    monkeypatch.setitem(config.LEGACY_MCP_DIRS, "gmail", legacy)
    # A named account must never silently borrow the default account's creds.
    assert auth.describe_source("gmail", account="kodamai") == "none"


def test_pa_store_takes_precedence_over_legacy(tmp_path, monkeypatch):
    legacy = tmp_path / "gmail-mcp"
    write_legacy(legacy, " ".join(GMAIL))
    monkeypatch.setitem(config.LEGACY_MCP_DIRS, "gmail", legacy)
    config.write_json(config.token_path("default"),
                      {"refresh_token": "rt", "scopes": auth.ALL_SCOPES})
    assert "pa store" in auth.describe_source("gmail")


def test_credentials_for_unknown_service():
    with pytest.raises(AuthError):
        auth.credentials_for("telepathy")


def test_credentials_for_missing_everything_mentions_setup(monkeypatch):
    monkeypatch.setattr(config, "LEGACY_MCP_DIRS", {})
    with pytest.raises(AuthError) as info:
        auth.credentials_for("gmail")
    assert "pa auth login" in str(info.value)


def test_credentials_for_wrong_scopes_suggests_force_login(monkeypatch):
    monkeypatch.setattr(config, "LEGACY_MCP_DIRS", {})
    config.write_json(config.token_path("default"),
                      {"refresh_token": "rt", "scopes": auth.SCOPES["calendar"]})
    with pytest.raises(AuthError) as info:
        auth.credentials_for("gmail")
    assert "--force" in str(info.value)


def test_client_file_accepts_installed_and_web_and_bare(tmp_path):
    for wrapper in ("installed", "web", None):
        payload = {"client_id": "c", "client_secret": "s"}
        path = tmp_path / f"client-{wrapper}.json"
        path.write_text(json.dumps({wrapper: payload} if wrapper else payload))
        assert auth._client_from_file(path)["client_id"] == "c"


def test_client_file_rejects_incomplete(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"installed": {"client_id": "c"}}))
    with pytest.raises(AuthError) as info:
        auth._client_from_file(path)
    assert "client_secret" in str(info.value)


def test_client_file_missing(tmp_path):
    with pytest.raises(AuthError):
        auth._client_from_file(tmp_path / "nope.json")


def test_token_is_written_with_owner_only_permissions():
    path = config.token_path("default")
    config.write_json(path, {"refresh_token": "secret"}, private=True)
    assert oct(path.stat().st_mode)[-3:] == "600"


def test_logout_removes_token_and_is_idempotent():
    config.write_json(config.token_path("default"), {"refresh_token": "rt"})
    assert auth.logout("default") is True
    assert auth.logout("default") is False


def test_account_resolution_precedence(monkeypatch):
    assert config.resolve_account() == "default"
    monkeypatch.setenv("PA_ACCOUNT", "from-env")
    assert config.resolve_account() == "from-env"
    assert config.resolve_account("explicit") == "explicit"


def test_config_default_account_used_when_env_absent(monkeypatch):
    monkeypatch.delenv("PA_ACCOUNT", raising=False)
    config.save_config({"default_account": "kodamai"})
    assert config.resolve_account() == "kodamai"


def test_list_accounts_only_counts_those_with_tokens():
    config.write_json(config.token_path("work"), {"refresh_token": "r"})
    config.account_dir("halfbaked").mkdir(parents=True, exist_ok=True)
    assert config.list_accounts() == ["work"]


def test_all_scopes_is_the_union():
    for service_scopes in auth.SCOPES.values():
        assert set(service_scopes) <= set(auth.ALL_SCOPES)
