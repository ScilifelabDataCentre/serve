"""
Waffle-controlled toggles for the background task framework.

These toggles are intentionally centralized here so the semantics (and switch
names) are consistent across the codebase.
"""

from __future__ import annotations

import waffle  # type: ignore

# When ON: deployments proceed even if critical background tasks failed.
# When OFF (default/missing): critical task failure blocks deployment.
BACKGROUND_TASKS_NONBLOCKING_DEPLOY_SWITCH = "background_tasks_nonblocking_deploy"


def background_tasks_nonblocking_deploy() -> bool:
    return waffle.switch_is_active(BACKGROUND_TASKS_NONBLOCKING_DEPLOY_SWITCH)
