"""Workbook contract definitions for phase-v1 valuation runs."""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
from typing import Iterable

PHASE_V1_TEMPLATE_FILENAME = (
    "Valuation_Template_TTM_TSM_RD_Lease_BankStyle_ExcelGraph_Logbook.xlsx"
)

PHASE_V1_REQUIRED_TABS: tuple[str, ...] = (
    "README",
    "Inputs",
    "Dilution (TSM)",
    "R&D Capitalization",
    "Lease Capitalization",
    "DCF",
    "Sensitivity",
    "Comps",
    "Checks",
    "Sources",
    "Story",
    "Output",
    "Agent Log",
)

PHASE_V1_REQUIRED_NAMED_RANGE_PATTERNS: tuple[str, ...] = (
    "log_run_id",
    "log_status",
    "log_start_ts",
    "log_end_ts",
    "inp_ticker",
    "inp_name",
    "inp_px",
    "inp_rf",
    "inp_erp",
    "inp_beta",
    "calc_ke",
    "calc_wacc",
    "inp_cash",
    "inp_debt",
    "calc_lease_debt",
    "inp_basic_shares",
    "calc_diluted_shares",
    "inp_tsm_tranche1_count_mm",
    "inp_tsm_tranche1_strike",
    "inp_tsm_tranche1_type",
    "inp_tsm_tranche1_note",
    "tsm_tranche_table",
    "out_tsm_incremental_shares",
    "out_tsm_diluted_shares",
    "inp_w_pess",
    "inp_w_base",
    "inp_w_opt",
    "inp_pess_g*",
    "inp_pess_m*",
    "inp_pess_tax",
    "inp_pess_wacc",
    "inp_pess_gt",
    "inp_base_g*",
    "inp_base_m*",
    "inp_base_tax",
    "inp_base_wacc",
    "inp_base_gt",
    "inp_opt_g*",
    "inp_opt_m*",
    "inp_opt_tax",
    "inp_opt_wacc",
    "inp_opt_gt",
    "out_value_ps_pess",
    "out_value_ps_base",
    "out_value_ps_opt",
    "out_value_ps_weighted",
    "out_equity_value_weighted",
    "out_enterprise_value_weighted",
    "[oO][uU][tT]_[wW][aA][cC][cC]",
    "out_terminal_g",
    "sens_base_value_ps",
    "sens_wacc_vector",
    "sens_terminal_g_vector",
    "sens_grid_values",
    "sens_grid_full",
    "comps_target_rev_ttm",
    "comps_target_ebit_ttm",
    "comps_header",
    "comps_firstrow",
    "comps_table",
    "comps_table_full",
    "comps_peer_tickers",
    "comps_peer_names",
    "comps_multiples_header",
    "comps_multiples_values",
    "comps_method_note",
    "comps_peer_count",
    "comps_multiple_count",
    "comps_ev_ebit",
    "comps_ev_sales",
    "comps_pe",
    "comps_notes",
    "sources_header",
    "sources_firstrow",
    "sources_table",
    "story_thesis",
    "story_growth",
    "story_profitability",
    "story_reinvestment",
    "story_risk",
    "story_sanity_checks",
    "story_grid_header",
    "story_grid_rows",
    "story_grid_citations",
    "story_memo_hooks",
    "log_actions_firstrow",
    "log_actions_table",
    "log_assumptions_firstrow",
    "log_assumptions_table",
    "log_story_firstrow",
    "log_story_table",
    "checks_statuses",
)


@dataclass(frozen=True)
class WorkbookContractValidation:
    """Validation output for a workbook against the phase-v1 contract."""

    missing_tabs: tuple[str, ...]
    missing_named_ranges: tuple[str, ...]

    @property
    def is_valid(self) -> bool:
        return not self.missing_tabs and not self.missing_named_ranges


@dataclass(frozen=True)
class WorkbookContract:
    """Required workbook structure and named-range interface."""

    template_filename: str
    required_tabs: tuple[str, ...]
    required_named_range_patterns: tuple[str, ...]

    def validate(
        self,
        sheet_names: Iterable[str],
        named_ranges: Iterable[str],
    ) -> WorkbookContractValidation:
        sheet_set = {name.strip() for name in sheet_names}
        named_set = {name.strip() for name in named_ranges}

        missing_tabs = tuple(
            tab for tab in self.required_tabs if tab not in sheet_set
        )
        missing_named_ranges = tuple(
            pattern
            for pattern in self.required_named_range_patterns
            if not any(fnmatch(name, pattern) for name in named_set)
        )

        return WorkbookContractValidation(
            missing_tabs=missing_tabs,
            missing_named_ranges=missing_named_ranges,
        )


def build_phase_v1_workbook_contract() -> WorkbookContract:
    """Build the default workbook contract for phase-v1 workflows."""
    return WorkbookContract(
        template_filename=PHASE_V1_TEMPLATE_FILENAME,
        required_tabs=PHASE_V1_REQUIRED_TABS,
        required_named_range_patterns=PHASE_V1_REQUIRED_NAMED_RANGE_PATTERNS,
    )
