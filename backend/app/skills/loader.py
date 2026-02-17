"""Filesystem skill loader for phase-v1 orchestration prompts."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SkillLoader:
    """Load and cache SKILL.md/reference text blocks from the repository."""

    repo_root: Path
    _cache: dict[str, str] = field(default_factory=dict, init=False, repr=False)

    def load_skill_markdown(self, skill_path: str) -> str:
        path = self.repo_root / skill_path / "SKILL.md"
        return self._read_cached(path)

    def load_shared_quality_bundle(self) -> str:
        base = self.repo_root / "skills" / "finance-quality-bar-and-evidence"
        sections: list[str] = [self._read_cached(base / "SKILL.md")]

        preferred_refs = (
            "quality-bar-and-standards.md",
            "source-priority-and-contradiction-policy.md",
            "high-impact-thresholds-and-question-policy.md",
            "google-sheets-execution-policy.md",
        )
        for filename in preferred_refs:
            sections.append(self._read_cached(base / "references" / filename))
        return "\n\n".join(section for section in sections if section)

    def load_phase_reference_bundle(self, phase: str) -> str:
        base = self.repo_root / "skills" / "finance-quality-bar-and-evidence" / "references"
        phase = phase.strip().lower()
        mapping: dict[str, tuple[str, ...]] = {
            "assumptions": (
                "sector-assumption-playbook.md",
                "high-impact-thresholds-and-question-policy.md",
            ),
            "validation": (
                "source-priority-and-contradiction-policy.md",
                "quality-bar-and-standards.md",
            ),
            "memo": (
                "sample-mini-memo.md",
                "quality-bar-and-standards.md",
            ),
            "publish": (
                "sample-sheet-log-entries.md",
                "quality-bar-and-standards.md",
            ),
        }
        files = mapping.get(phase, ())
        return "\n\n".join(self._read_cached(base / filename) for filename in files)

    def _read_cached(self, path: Path) -> str:
        key = str(path)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        if not path.exists():
            self._cache[key] = ""
            return ""
        text = path.read_text(encoding="utf-8")
        self._cache[key] = text
        return text
