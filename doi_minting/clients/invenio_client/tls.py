from __future__ import annotations

import os
from typing import Union

VerifyType = Union[bool, str]


def parse_tls_verify(value: str | None) -> VerifyType:
    """Map env text to requests.verify value: True/False or a cert path."""
    if value is None:
        return True  # default: verify on
    v = value.strip()
    lv = v.lower()
    if lv in ("", "1", "true", "yes", "on"):
        return True
    if lv in ("0", "false", "no", "off"):
        return False
    # Treat anything else as a path (expand ~)
    return os.path.expanduser(v)


def tls_verify_from_env(env_var: str = "TLS_SSL_VERIFICATION") -> VerifyType:
    return parse_tls_verify(os.getenv(env_var))
