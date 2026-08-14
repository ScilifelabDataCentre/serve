from types import SimpleNamespace

import pytest

from common.templatetags.is_login_signup_disabled import is_login_signup_disabled


@pytest.mark.parametrize("items", [None, []])
def test_is_login_signup_disabled_returns_false_for_missing_items(items):
    assert is_login_signup_disabled(items) is False


def test_is_login_signup_disabled_returns_false_when_all_items_are_enabled():
    items = [SimpleNamespace(login_and_signup_disabled=False)]

    assert is_login_signup_disabled(items) is False


def test_is_login_signup_disabled_returns_true_when_an_item_disables_login_and_signup():
    items = [
        SimpleNamespace(login_and_signup_disabled=False),
        SimpleNamespace(login_and_signup_disabled=True),
    ]

    assert is_login_signup_disabled(items) is True
