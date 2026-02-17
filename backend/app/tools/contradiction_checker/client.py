"""Source contradiction checker interface."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from ..contracts import DataSourceCitation
from ..research_contracts import ContradictionFlag


class ContradictionChecker(Protocol):
    """Detect contradictions across multi-source financial facts."""

    def check_contradictions(
        self,
        ticker: str,
        facts: dict[str, Any],
        citations: list[DataSourceCitation],
    ) -> list[ContradictionFlag]:
        """Return contradiction flags for human/agent review."""


@dataclass
class RuleBasedContradictionChecker:
    """Rule-based contradiction checks across provider-normalized facts."""

    numeric_relative_tolerance: float = 0.12

    def check_contradictions(
        self,
        ticker: str,
        facts: dict[str, Any],
        citations: list[DataSourceCitation],
    ) -> list[ContradictionFlag]:
        del ticker
        del citations

        flags: list[ContradictionFlag] = []
        for metric_key, raw_values in facts.items():
            source_values = self._extract_source_values(raw_values)
            if len(source_values) < 2:
                continue

            source_values.sort(key=lambda item: self._source_priority(item[0]))
            anchor_source, anchor_value = source_values[0]
            for source, value in source_values[1:]:
                flag = self._build_flag(
                    metric_key=metric_key,
                    source_a=anchor_source,
                    value_a=anchor_value,
                    source_b=source,
                    value_b=value,
                )
                if flag is not None:
                    flags.append(flag)
        return flags

    def _extract_source_values(self, raw_values: Any) -> list[tuple[str, Any]]:
        values: list[tuple[str, Any]] = []

        if isinstance(raw_values, dict):
            if isinstance(raw_values.get("values"), list):
                for row in raw_values["values"]:
                    if not isinstance(row, dict):
                        continue
                    source = str(row.get("source", "")).strip().lower()
                    value = row.get("value")
                    if source:
                        values.append((source, value))
                return values

            for source, value in raw_values.items():
                if source in {"value", "unit", "as_of", "timestamp"}:
                    continue
                if not isinstance(source, str):
                    continue
                source_key = source.strip().lower()
                if source_key:
                    values.append((source_key, value))
            return values

        if isinstance(raw_values, list):
            for row in raw_values:
                if not isinstance(row, dict):
                    continue
                source = str(row.get("source", "")).strip().lower()
                if not source:
                    continue
                values.append((source, row.get("value")))
        return values

    def _build_flag(
        self,
        *,
        metric_key: str,
        source_a: str,
        value_a: Any,
        source_b: str,
        value_b: Any,
    ) -> ContradictionFlag | None:
        numeric_a = self._to_float(value_a)
        numeric_b = self._to_float(value_b)
        if numeric_a is not None and numeric_b is not None:
            if numeric_a == 0:
                if numeric_b == 0:
                    return None
                rel_diff = 1.0
            else:
                rel_diff = abs(numeric_a - numeric_b) / abs(numeric_a)
            if rel_diff <= self.numeric_relative_tolerance:
                return None
            severity = "high" if rel_diff >= 0.25 else "medium"
            return ContradictionFlag(
                metric_key=metric_key,
                source_a=source_a,
                source_b=source_b,
                message=(
                    f"{metric_key} mismatch: {source_a}={numeric_a}, "
                    f"{source_b}={numeric_b}, rel_diff={rel_diff:.2%}"
                ),
                severity=severity,
            )

        text_a = str(value_a).strip()
        text_b = str(value_b).strip()
        if text_a == text_b:
            return None
        return ContradictionFlag(
            metric_key=metric_key,
            source_a=source_a,
            source_b=source_b,
            message=f"{metric_key} mismatch: {source_a}='{text_a}' vs {source_b}='{text_b}'",
            severity="medium",
        )

    def _source_priority(self, source: str) -> int:
        normalized = source.strip().lower()
        if normalized in {"sec", "sec_edgar", "fred", "treasury"}:
            return 0
        if normalized in {"alpha_vantage"}:
            return 1
        if normalized in {"finnhub"}:
            return 2
        if normalized in {"tavily", "web", "news"}:
            return 3
        return 4

    def _to_float(self, value: Any) -> float | None:
        try:
            if value in (None, ""):
                return None
            return float(value)
        except (TypeError, ValueError):
            return None
