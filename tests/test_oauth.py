from urllib.parse import parse_qs, urlparse

import pytest

from ali1688_uploader.config import Settings
from ali1688_uploader.oauth import (
    Alibaba1688OAuthClient,
    TokenResult,
    build_authorization_url,
    write_tokens_to_env,
)


def _result() -> TokenResult:
    return TokenResult.from_payload(
        {
            "access_token": "access-secret",
            "refresh_token": "refresh-secret",
            "expires_in": "36000",
            "memberId": "member-1",
        }
    )


def test_build_authorization_url():
    url = build_authorization_url(
        "app-key",
        "https://example.com/callback?a=1",
        state="csrf-state",
    )
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    assert parsed.scheme == "https"
    assert parsed.netloc == "auth.1688.com"
    assert query["client_id"] == ["app-key"]
    assert query["site"] == ["1688"]
    assert query["redirect_uri"] == ["https://example.com/callback?a=1"]
    assert query["state"] == ["csrf-state"]


def test_safe_summary_does_not_expose_tokens():
    summary = _result().safe_summary()
    text = repr(summary)
    assert "access-secret" not in text
    assert "refresh-secret" not in text
    assert summary["access_token_received"] is True
    assert summary["refresh_token_received"] is True


def test_write_tokens_to_env_upserts_without_losing_other_settings(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "ALI1688_APP_KEY=abc\n"
        "ALI1688_ACCESS_TOKEN=old-access\n"
        "ALI1688_REFRESH_TOKEN=old-refresh\n",
        encoding="utf-8",
    )
    write_tokens_to_env(env, _result())
    content = env.read_text(encoding="utf-8")
    assert "ALI1688_APP_KEY=abc" in content
    assert "old-access" not in content
    assert "old-refresh" not in content
    assert "ALI1688_ACCESS_TOKEN=access-secret" in content
    assert "ALI1688_REFRESH_TOKEN=refresh-secret" in content


class _ErrorResponse:
    status_code = 400

    def json(self):
        return {"error": "invalid_grant", "message": "authorization code expired"}


def test_oauth_http_error_does_not_include_app_secret():
    client = Alibaba1688OAuthClient(
        Settings(
            app_key="app-key",
            app_secret="SUPER-SECRET-APP-SECRET",
            access_token="",
        )
    )
    with pytest.raises(RuntimeError) as exc:
        client._decode(_ErrorResponse())
    assert "SUPER-SECRET-APP-SECRET" not in str(exc.value)
    assert "invalid_grant" in str(exc.value)
