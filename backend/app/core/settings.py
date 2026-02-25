"""Runtime settings for V1 backend services."""

from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    app_env: str = "dev"
    llm_provider: str = "google"
    llm_model: str = "gemini-3"
    memo_llm_model: str = "gemini-3-pro-preview"
    memo_min_infographics: int = 6
    memo_max_infographics: int = 7
    google_api_key: str = ""
    google_auth_mode: str = "oauth"
    google_oauth_client_secret_file: str = "credentials.json"
    google_oauth_token_file: str = "token.json"
    sec_api_user_agent: str = "finance-research-agent/0.1 (name@domain.com)"
    sec_contact_email: str = ""
    fundamentals_provider: str = "finnhub"
    market_data_provider: str = "finnhub"
    news_provider: str = "tavily"
    web_search_provider: str = "tavily"
    rates_provider: str = "fred"
    transcript_provider: str = "alpha_vantage"
    corporate_actions_provider: str = "alpha_vantage"
    peer_provider: str = "finnhub"
    contradiction_checker_provider: str = "rule_based"
    finnhub_api_key: str = ""
    alpha_vantage_api_key: str = ""
    tavily_api_key: str = ""
    fred_api_key: str = ""
    fred_rf_series_id: str = "DGS10"
    default_equity_risk_premium: float = 0.05
    default_cost_of_debt: float = 0.055
    default_debt_weight: float = 0.10
    default_terminal_growth: float = 0.025
    default_growth_year_1: float = 0.05
    default_growth_year_2: float = 0.04
    default_growth_year_3: float = 0.03
    default_growth_year_4: float = 0.03
    default_growth_year_5: float = 0.03
    default_margin_year_5: float = 0.30
    default_margin_year_10: float = 0.30
    default_tax_norm: float = 0.18
    default_da_pct: float = 0.03
    default_capex_pct: float = 0.02
    default_nwc_pct: float = 0.00
    default_rd_pct: float = 0.07
    default_rent_pct: float = 0.01
    default_other_adjustment: float = 0.0
    default_cap_rd_toggle: str = "YES"
    default_cap_lease_toggle: str = "YES"
    news_lookback_days: int = 14
    sheets_template_file: str = (
        "Valuation_Template_TTM_TSM_RD_Lease_BankStyle_ExcelGraph_Logbook.xlsx"
    )
    sheets_logbook_file: str = "Valuation_Agent_Logbook_ExcelGraph.xlsx"


def load_settings() -> Settings:
    """Load settings from environment with V1 defaults."""
    return Settings(
        app_env=os.getenv("APP_ENV", "dev"),
        llm_provider=os.getenv("LLM_PROVIDER", "google"),
        llm_model=os.getenv("LLM_MODEL", "gemini-3"),
        memo_llm_model=os.getenv("MEMO_LLM_MODEL", "gemini-3-pro-preview"),
        memo_min_infographics=int(os.getenv("MEMO_MIN_INFOGRAPHICS", "6")),
        memo_max_infographics=int(os.getenv("MEMO_MAX_INFOGRAPHICS", "7")),
        google_api_key=os.getenv("GOOGLE_API_KEY", ""),
        google_auth_mode=os.getenv("GOOGLE_AUTH_MODE", "oauth"),
        google_oauth_client_secret_file=os.getenv(
            "GOOGLE_OAUTH_CLIENT_SECRET_FILE", "credentials.json"
        ),
        google_oauth_token_file=os.getenv("GOOGLE_OAUTH_TOKEN_FILE", "token.json"),
        sec_api_user_agent=os.getenv(
            "SEC_API_USER_AGENT", "finance-research-agent/0.1 (name@domain.com)"
        ),
        sec_contact_email=os.getenv("SEC_CONTACT_EMAIL", ""),
        fundamentals_provider=os.getenv("FUNDAMENTALS_PROVIDER", "finnhub"),
        market_data_provider=os.getenv("MARKET_DATA_PROVIDER", "finnhub"),
        news_provider=os.getenv("NEWS_PROVIDER", "tavily"),
        web_search_provider=os.getenv("WEB_SEARCH_PROVIDER", "tavily"),
        rates_provider=os.getenv("RATES_PROVIDER", "fred"),
        transcript_provider=os.getenv("TRANSCRIPT_PROVIDER", "alpha_vantage"),
        corporate_actions_provider=os.getenv(
            "CORPORATE_ACTIONS_PROVIDER", "alpha_vantage"
        ),
        peer_provider=os.getenv("PEER_PROVIDER", "finnhub"),
        contradiction_checker_provider=os.getenv(
            "CONTRADICTION_CHECKER_PROVIDER", "rule_based"
        ),
        finnhub_api_key=os.getenv("FINNHUB_API_KEY", ""),
        alpha_vantage_api_key=os.getenv("ALPHA_VANTAGE_API_KEY", ""),
        tavily_api_key=os.getenv("TAVILY_API_KEY", ""),
        fred_api_key=os.getenv("FRED_API_KEY", ""),
        fred_rf_series_id=os.getenv("FRED_RF_SERIES_ID", "DGS10"),
        default_equity_risk_premium=float(
            os.getenv("DEFAULT_EQUITY_RISK_PREMIUM", "0.05")
        ),
        default_cost_of_debt=float(os.getenv("DEFAULT_COST_OF_DEBT", "0.055")),
        default_debt_weight=float(os.getenv("DEFAULT_DEBT_WEIGHT", "0.10")),
        default_terminal_growth=float(os.getenv("DEFAULT_TERMINAL_GROWTH", "0.025")),
        default_growth_year_1=float(os.getenv("DEFAULT_GROWTH_YEAR_1", "0.05")),
        default_growth_year_2=float(os.getenv("DEFAULT_GROWTH_YEAR_2", "0.04")),
        default_growth_year_3=float(os.getenv("DEFAULT_GROWTH_YEAR_3", "0.03")),
        default_growth_year_4=float(os.getenv("DEFAULT_GROWTH_YEAR_4", "0.03")),
        default_growth_year_5=float(os.getenv("DEFAULT_GROWTH_YEAR_5", "0.03")),
        default_margin_year_5=float(os.getenv("DEFAULT_MARGIN_YEAR_5", "0.30")),
        default_margin_year_10=float(os.getenv("DEFAULT_MARGIN_YEAR_10", "0.30")),
        default_tax_norm=float(os.getenv("DEFAULT_TAX_NORM", "0.18")),
        default_da_pct=float(os.getenv("DEFAULT_DA_PCT", "0.03")),
        default_capex_pct=float(os.getenv("DEFAULT_CAPEX_PCT", "0.02")),
        default_nwc_pct=float(os.getenv("DEFAULT_NWC_PCT", "0.00")),
        default_rd_pct=float(os.getenv("DEFAULT_RD_PCT", "0.07")),
        default_rent_pct=float(os.getenv("DEFAULT_RENT_PCT", "0.01")),
        default_other_adjustment=float(os.getenv("DEFAULT_OTHER_ADJUSTMENT", "0.0")),
        default_cap_rd_toggle=os.getenv("DEFAULT_CAP_RD_TOGGLE", "YES"),
        default_cap_lease_toggle=os.getenv("DEFAULT_CAP_LEASE_TOGGLE", "YES"),
        news_lookback_days=int(os.getenv("NEWS_LOOKBACK_DAYS", "14")),
        sheets_template_file=os.getenv(
            "SHEETS_TEMPLATE_FILE",
            "Valuation_Template_TTM_TSM_RD_Lease_BankStyle_ExcelGraph_Logbook.xlsx",
        ),
        sheets_logbook_file=os.getenv(
            "SHEETS_LOGBOOK_FILE", "Valuation_Agent_Logbook_ExcelGraph.xlsx"
        ),
    )
