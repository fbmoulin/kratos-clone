"""Coverage for the semantic-lookup helper used by the design-system generators.

Phase 2 of ROADMAP. Locks down `find_button_by_classes()` so the generators
no longer IndexError on non-NexusFlow sites. The helper is duplicated across
`scripts/generate_design_system_v{1,2}.py` (single-script style by design);
the test inlines an identical copy to avoid importing the side-effecty scripts.
"""

from __future__ import annotations
import pytest


# ── Inline copy of helper from scripts/generate_design_system_v{1,2}.py ─────


def find_button_by_classes(buttons, *required, default_label: str = "Action"):
    for b in buttons:
        cls = b.get("classes", "")
        if all(s in cls for s in required):
            return {"classes": cls, "label": b.get("label", "") or default_label}
    return {"classes": "", "label": default_label}


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def nexusflow_buttons():
    """Reproduces the inv['buttons'] shape from a real NexusFlow capture."""
    return [
        {  # idx 0 — ghost nav
            "classes": "px-4 py-2 rounded-full bg-white/5 hover:bg-white/10 border border-white/10",
            "label": "Get Started",
        },
        {  # idx 1 — mobile menu (no label)
            "classes": "md:hidden text-white text-2xl",
            "label": "",
        },
        {  # idx 2 — primary CTA
            "classes": "px-6 py-2.5 rounded-full bg-gradient-to-r from-orange-500 to-orange-600 text-white border border-orange-400/50",
            "label": "Start for free",
        },
        {  # idx 3 — secondary CTA
            "classes": "px-6 py-2.5 rounded-full bg-neutral-900/60 border border-neutral-800 text-neutral-300",
            "label": "View demo",
        },
    ]


# ── Behavior ─────────────────────────────────────────────────────────────────


def test_finds_primary_cta_by_signature(nexusflow_buttons):
    """Match by Tailwind signature, not by hardcoded index."""
    result = find_button_by_classes(nexusflow_buttons, "gradient-to-r", "from-orange")
    assert "from-orange-500" in result["classes"]
    assert result["label"] == "Start for free"


def test_finds_secondary_by_neutral_signature(nexusflow_buttons):
    result = find_button_by_classes(
        nexusflow_buttons, "neutral-900/", "border-neutral-800"
    )
    assert "neutral-900/60" in result["classes"]


def test_finds_ghost_nav_by_white_glass_signature(nexusflow_buttons):
    result = find_button_by_classes(nexusflow_buttons, "white/5", "white/10")
    assert "white/5" in result["classes"]
    assert result["label"] == "Get Started"


def test_returns_default_when_no_match(nexusflow_buttons):
    """Site without orange brand → no match → default-label stub returned."""
    result = find_button_by_classes(
        nexusflow_buttons, "from-purple", "to-pink", default_label="Sign up"
    )
    assert result == {"classes": "", "label": "Sign up"}


def test_returns_first_match_when_multiple(nexusflow_buttons):
    """If multiple buttons qualify, first wins."""
    result = find_button_by_classes(nexusflow_buttons, "rounded-full")
    # First button has rounded-full
    assert result["classes"] == nexusflow_buttons[0]["classes"]


def test_empty_label_replaced_by_default(nexusflow_buttons):
    """Mobile menu (idx 1) has empty label → default fills in."""
    result = find_button_by_classes(
        nexusflow_buttons, "md:hidden", default_label="Menu"
    )
    assert result["label"] == "Menu"


def test_works_with_zero_buttons():
    """Empty inventory → default stub, no IndexError."""
    result = find_button_by_classes([], "anything", default_label="Empty")
    assert result == {"classes": "", "label": "Empty"}


def test_works_with_no_required_substrings(nexusflow_buttons):
    """No requirements → first button matches (all() of empty list is True)."""
    result = find_button_by_classes(nexusflow_buttons)
    assert result["classes"] == nexusflow_buttons[0]["classes"]


def test_partial_match_is_rejected(nexusflow_buttons):
    """One substring matches, another doesn't → no match."""
    result = find_button_by_classes(
        nexusflow_buttons, "gradient-to-r", "from-cyan", default_label="Stub"
    )
    assert result["classes"] == ""
    assert result["label"] == "Stub"


# ── Regression test for the audit P1-C IndexError ───────────────────────────


def test_p1c_no_indexerror_on_short_inventory():
    """A site with only 2 buttons used to crash the v1 generator with
    `inv["buttons"][7]` → IndexError. Helper returns default stub instead."""
    short = [
        {"classes": "btn-a", "label": "A"},
        {"classes": "btn-b", "label": "B"},
    ]
    # Old behavior: inv["buttons"][7] → IndexError
    # New behavior: returns default stub
    result = find_button_by_classes(short, "nonexistent")
    assert result["classes"] == ""  # no crash
