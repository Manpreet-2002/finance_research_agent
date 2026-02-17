"""High-level valuation orchestration service for V1 deterministic LangGraph runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..core.logging import setup_run_logger, teardown_run_logger
from ..core.settings import Settings, load_settings
from ..llm.langchain_gemini import LangChainGeminiClient
from ..schemas.valuation_run import ValuationRunRequest, ValuationRunResult
from ..sheets.engine import SheetsEngine
from ..sheets.google_engine import GoogleSheetsEngine
from ..skills.loader import SkillLoader
from ..skills.router import SkillRouter
from ..tools.data_service import DataService
from ..tools.fundamentals.client import SecEdgarFundamentalsClient
from ..tools.llm_tools import LlmToolRegistry, build_phase_v1_tool_registry
from ..tools.provider_factory import build_data_service, build_research_service
from ..tools.research_service import ResearchService
from .langgraph_finance_agent import LangGraphFinanceAgent
from .state_machine import V1WorkflowStateMachine


@dataclass
class ValuationRunner:
    """Coordinates phase-v1 tools, sheets engine, and LangGraph execution."""

    settings: Settings | None = None
    data_service: DataService | None = None
    research_service: ResearchService | None = None
    sheets_engine: SheetsEngine | None = None
    llm_client: LangChainGeminiClient | None = None
    tool_registry: LlmToolRegistry | None = None
    _agent: LangGraphFinanceAgent | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        resolved_settings = self.settings or load_settings()
        self.settings = resolved_settings

        if self.data_service is None:
            self.data_service = build_data_service(resolved_settings)
        if self.research_service is None:
            self.research_service = build_research_service(resolved_settings)
        if self.sheets_engine is None:
            self.sheets_engine = GoogleSheetsEngine(resolved_settings)

        if self.llm_client is None:
            self.llm_client = LangChainGeminiClient(
                api_key=resolved_settings.google_api_key,
                model=resolved_settings.llm_model,
                temperature=0.1,
            )

        if self.tool_registry is None:
            sec_client = SecEdgarFundamentalsClient(
                user_agent=resolved_settings.sec_api_user_agent,
                contact_email=resolved_settings.sec_contact_email,
            )
            self.tool_registry = build_phase_v1_tool_registry(
                data_service=self.data_service,
                research_service=self.research_service,
                sheets_engine=self.sheets_engine,
                sec_fundamentals_client=sec_client,
            )

        repo_root = Path(__file__).resolve().parents[3]
        self._agent = LangGraphFinanceAgent(
            llm_client=self.llm_client,
            tool_registry=self.tool_registry,
            sheets_engine=self.sheets_engine,
            skill_router=SkillRouter(),
            state_machine=V1WorkflowStateMachine(),
            skill_loader=SkillLoader(repo_root=repo_root),
        )

    def run(self, request: ValuationRunRequest) -> ValuationRunResult:
        if self._agent is None:
            raise RuntimeError("ValuationRunner agent not initialized.")
        logger, handler, log_path = setup_run_logger(request.run_id)
        logger.info(
            "run_start run_id=%s ticker=%s model=%s",
            request.run_id,
            request.ticker,
            self.settings.llm_model if self.settings else "unknown",
        )
        try:
            result = self._agent.run(request)
            logger.info(
                "run_end run_id=%s status=%s spreadsheet_id=%s phases=%s",
                result.run_id,
                result.status,
                result.spreadsheet_id,
                ",".join(result.phases_executed),
            )
            if result.notes:
                logger.info("run_notes run_id=%s notes=%s", result.run_id, result.notes)
            return result
        finally:
            logger.info("run_log_path run_id=%s path=%s", request.run_id, log_path)
            teardown_run_logger(logger, handler)
