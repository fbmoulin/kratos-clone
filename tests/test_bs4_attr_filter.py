"""Pins beautifulsoup4's attribute-presence filter contract.

`find_all(name=None, attrs={KEY: True})` selects every element carrying KEY regardless
of value — including an empty value. That presence-not-truthiness guarantee is the
invariant the `downloader.py` capture path relies on when it reads the matched
attribute off each element.

Scope, stated plainly: these tests do NOT detect a revert of the `name=None` call form.
That form is runtime-invisible on every bs4 version tested (4.14.3 and 4.15.0) — it
exists only in the type stubs' overload set, so only a type-checker can see it. The
guard against a revert is the unpinned `forward-compat` CI job, which type-checks
against the latest bs4 from PyPI. What these tests DO catch is bs4 changing presence
semantics underneath us, which would silently break the capture path.
"""

import pytest
from bs4 import BeautifulSoup

HTML = (
    '<p style="a">one</p>'
    '<div style="">two</div>'
    '<span data-background="y">three</span>'
    '<img src="x.png">'
    "<b>no-attrs</b>"
)


def _soup() -> BeautifulSoup:
    return BeautifulSoup(HTML, "html.parser")


@pytest.mark.parametrize(
    ("key", "expected_texts"),
    [
        ("style", ["one", "two"]),
        ("data-background", ["three"]),
        ("src", [""]),
    ],
)
def test_attr_presence_filter_selects_elements_carrying_the_key(key, expected_texts):
    found = _soup().find_all(name=None, attrs={key: True})
    assert [el.get_text() for el in found] == expected_texts


def test_empty_attribute_value_still_counts_as_present():
    """`style=""` must match: the filter tests presence, not truthiness."""
    found = _soup().find_all(name=None, attrs={"style": True})
    assert any(el.get("style") == "" for el in found), "empty-valued attribute must match"


def test_element_without_the_attribute_is_excluded():
    found = _soup().find_all(name=None, attrs={"style": True})
    assert all(el.name != "b" for el in found)


def test_every_match_carries_the_attribute():
    """The invariant the three downloader.py call sites rely on before subscripting."""
    for key in ("style", "data-background", "src"):
        for el in _soup().find_all(name=None, attrs={key: True}):
            assert el.get(key) is not None, f"{el.name} matched on {key} but lacks it"
