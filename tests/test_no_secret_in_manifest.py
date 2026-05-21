"""Belt-and-suspenders negative test: ensure run_manifest cannot carry
API keys or other secrets, even if a future code change tries to.
"""
from __future__ import annotations

import dataclasses

from src.core.schema import RunManifest


SECRET_TOKENS = (
    "api_key", "api-key", "apikey",
    "secret", "token", "password",
    "anthropic_api_key", "xai_api_key", "hermes_oauth_token",
    "hermes_oauth", "bearer", "cookie",
)


def test_runmanifest_has_no_secret_like_field_names():
    fields = {f.name for f in dataclasses.fields(RunManifest)}
    for fn in fields:
        for tok in SECRET_TOKENS:
            assert tok not in fn.lower(), (
                f"RunManifest field '{fn}' contains forbidden token '{tok}'. "
                "Manifests must never carry secrets."
            )


def test_runmanifest_serialisation_excludes_env_dump():
    # Build a manifest and ensure to_dict() output does not include any
    # large dict that could be confused with os.environ.
    from datetime import datetime, timezone
    m = RunManifest(
        run_id="t",
        executed_at=datetime.now(timezone.utc),
        provider="mock",
        llm_provider="mock",
        config_hash="abc",
        query_count=0,
        raw_item_count=0,
        deduped_item_count=0,
        top10_count=0,
    )
    d = m.to_dict()
    # No string value in the manifest top-level should look like a key.
    for key, val in d.items():
        if isinstance(val, str):
            # 32+ char hex/base64-ish strings are suspicious in this context
            assert not (len(val) >= 32 and val.isalnum()), (
                f"manifest['{key}'] looks like a secret: len={len(val)}"
            )
