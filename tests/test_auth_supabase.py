from auth_supabase import SupabaseAuth, bearer_token


def test_disabled_without_config():
    assert SupabaseAuth("", "").enabled is False
    assert SupabaseAuth("https://x.supabase.co", "").enabled is False
    assert SupabaseAuth("https://x.supabase.co", "anon").enabled is True


def test_url_trailing_slash_is_stripped():
    assert SupabaseAuth("https://x.supabase.co/", "anon").url == "https://x.supabase.co"


def test_verify_token_uses_injected_verify():
    auth = SupabaseAuth(
        "https://x.supabase.co", "anon",
        verify=lambda t: {"id": "u1", "email": "a@b.com"} if t == "ok" else None,
    )
    assert auth.verify_token("ok") == {"id": "u1", "email": "a@b.com"}
    assert auth.verify_token("bad") is None


def test_verify_token_caches_valid_results():
    calls = []

    def verify(token):
        calls.append(token)
        return {"id": "u1", "email": "a@b.com"}

    auth = SupabaseAuth("https://x.supabase.co", "anon", verify=verify)
    auth.verify_token("ok")
    auth.verify_token("ok")
    assert calls == ["ok"]  # la segunda vez sale de la caché


def test_verify_token_returns_none_when_disabled():
    auth = SupabaseAuth("", "", verify=lambda t: {"id": "u1"})
    assert auth.verify_token("ok") is None


def test_bearer_token_parsing():
    class FakeRequest:
        def __init__(self, headers):
            self.headers = headers

    assert bearer_token(FakeRequest({"Authorization": "Bearer abc"})) == "abc"
    assert bearer_token(FakeRequest({"Authorization": "bearer xyz"})) == "xyz"
    assert bearer_token(FakeRequest({})) == ""
