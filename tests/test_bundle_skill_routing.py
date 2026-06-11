from __future__ import annotations

import re
from pathlib import Path

import pytest

SKILL_NAMES = (
    "slopgate-hygiene-orchestrator",
    "slopgate-code-hygiene-refactor",
    "slopgate-code-smell-utility-locator",
    "slopgate-intelligent-coding-patterns",
    "slopgate-test-extender",
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = REPO_ROOT / "bundle" / "shared" / "skills"
ROUTING_FRAGMENT = (
    REPO_ROOT
    / "src"
    / "slopgate"
    / "resources"
    / "bundle"
    / "shared"
    / "prompt-fragments"
    / "slopgate-skill-routing.md"
)


def _skill_text(skill_name: str) -> str:
    return (SKILL_ROOT / skill_name / "SKILL.md").read_text(encoding="utf-8")


def _frontmatter(text: str) -> str:
    assert text.startswith("---\n"), "skill must start with YAML frontmatter"
    marker = text.find("\n---\n", 4)
    assert marker != -1, "skill frontmatter must be closed"
    return text[4:marker]


def _description_from_frontmatter(frontmatter: str) -> str:
    match = re.search(r"^description: \|\n(?P<body>(?:  .*\n?)+)", frontmatter, re.M)
    assert match, "description must be a YAML block scalar"
    return "\n".join(line[2:] for line in match.group("body").splitlines())


@pytest.mark.parametrize("skill_name", SKILL_NAMES)
def test_slopgate_skills_have_findable_activation_contract(skill_name: str) -> None:
    text = _skill_text(skill_name)
    frontmatter = _frontmatter(text)
    description = _description_from_frontmatter(frontmatter)

    assert f"name: {skill_name}" in frontmatter, "frontmatter name must match directory"
    assert 80 <= len(description) <= 1024, "description should be useful but loader-safe"
    assert "metadata:" in frontmatter, "skill should expose machine-readable metadata"
    assert "hermes:" in frontmatter, "skill should expose Hermes tags for discovery"
    assert "slopgate:" in frontmatter, "skill should expose Slopgate activation metadata"
    assert "## When to Use" in text, "skill needs positive activation boundaries"
    assert "## When Not to Use" in text, "skill needs negative activation boundaries"


@pytest.mark.parametrize("skill_name", SKILL_NAMES)
def test_routing_fragment_mentions_each_slopgate_skill(skill_name: str) -> None:
    fragment = ROUTING_FRAGMENT.read_text(encoding="utf-8")

    assert skill_name in fragment, "routing fragment must mention every shared skill"


def test_routing_fragment_prefers_one_primary_skill() -> None:
    fragment = ROUTING_FRAGMENT.read_text(encoding="utf-8")

    assert "one primary skill first" in fragment, "agents need anti-buffet routing guidance"
    assert "Selection order" in fragment, "agents need precedence when triggers overlap"
    assert "Do not load all five" in fragment, "routing should prevent over-activation"


def test_bundle_skills_do_not_embed_source_checkout_paths() -> None:
    combined = "\n".join(_skill_text(name) for name in SKILL_NAMES)

    assert ".openclaw/workspace-hooker" not in combined, "skills must not require source checkouts"
    assert "/home/trav/.openclaw" not in combined, "skills must be usable from installed bundles"
