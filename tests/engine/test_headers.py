from sharpit.engine.headers import security_headers

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline';"
    " img-src 'self' data:; font-src 'self' data:; connect-src 'self';"
    " object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
)
PERMS = "accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), payment=(), usb=()"


# ported: BootUiSecurityHeadersTests.canonicalHeadersContainTheCompleteBrowserPolicy
def test_exact_policy_headers():
    h = dict(security_headers("shell"))
    assert h["Content-Security-Policy"] == CSP
    assert h["X-Content-Type-Options"] == "nosniff"
    assert h["X-Frame-Options"] == "DENY"
    assert h["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert h["Permissions-Policy"] == PERMS


# ported: BootUiSecurityHeadersTests.apiResponsesAreNeverCached, onlyContentHashedAssetsAreImmutable
def test_cache_per_kind():
    api = dict(security_headers("api"))
    assert api["Cache-Control"] == "no-store, must-revalidate"
    assert api["Pragma"] == "no-cache"
    shell = dict(security_headers("shell"))
    assert shell["Cache-Control"] == "no-cache"
    assert shell["Pragma"] == "no-cache"
    asset = dict(security_headers("asset"))
    assert asset["Cache-Control"] == "public, max-age=31536000, immutable"
    assert "Pragma" not in asset
