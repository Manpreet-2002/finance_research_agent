"""Spreadsheet engine interface for valuation workflows."""

from __future__ import annotations

from typing import Protocol

from ..workbook.inspection import WorkbookInspection


class SheetsEngine(Protocol):
    """Contract for the Google Sheets compute layer."""

    def copy_template(self, run_id: str, ticker: str) -> str:
        """Create a run spreadsheet from the template and return spreadsheet_id."""

    def write_named_ranges(self, spreadsheet_id: str, values: dict[str, object]) -> None:
        """Write inputs/toggles using named ranges."""

    def read_outputs(self, spreadsheet_id: str) -> dict[str, object]:
        """Read output contract ranges from the run spreadsheet."""

    def read_named_ranges(
        self,
        spreadsheet_id: str,
        names: list[str],
        *,
        value_render_option: str = "UNFORMATTED_VALUE",
    ) -> dict[str, list[list[object]]]:
        """Read existing named ranges only with raw grid values."""

    def append_named_table_rows(
        self,
        spreadsheet_id: str,
        table_name: str,
        rows: list[list[object]],
    ) -> None:
        """Append rows into a named table range (first empty row policy)."""

    def write_named_table(
        self,
        spreadsheet_id: str,
        table_name: str,
        rows: list[list[object]],
    ) -> None:
        """Overwrite a named table range from its top-left anchor."""

    def inspect_workbook(self, spreadsheet_id: str) -> WorkbookInspection:
        """Return tab + named-range metadata for contract validation."""

    def append_logbook_run(self, summary_row: list[object]) -> None:
        """Append a single row into the centralized Runs logbook tab."""

    def set_anyone_with_link_reader(self, spreadsheet_id: str) -> dict[str, object]:
        """Set sharing to "anyone with the link" reader and return API metadata."""
