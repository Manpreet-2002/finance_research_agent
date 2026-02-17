"""External data adapters and canonicalization services."""

from .contracts import (
    CanonicalValuationDataset,
    CompanyFundamentals,
    DataSourceCitation,
    DEFAULT_DCF_INPUT_ASSUMPTIONS,
    MarketSnapshot,
    NewsItem,
    REQUIRED_DCF_INPUT_RANGES,
    RatesSnapshot,
    TsmSnapshot,
)
from .data_service import DataService
from .llm_tools import LlmToolRegistry, ToolSpec, build_phase_v1_tool_registry
from .provider_factory import (
    ProviderConfigError,
    ProviderSelection,
    ResearchProviderSelection,
    build_data_service,
    build_research_service,
)
from .research_contracts import (
    ContradictionFlag,
    CorporateAction,
    PeerCompany,
    ResearchPacket,
    TranscriptSignal,
)
from .research_service import ResearchService

__all__ = [
    "CanonicalValuationDataset",
    "ContradictionFlag",
    "CorporateAction",
    "CompanyFundamentals",
    "DataService",
    "DataSourceCitation",
    "DEFAULT_DCF_INPUT_ASSUMPTIONS",
    "LlmToolRegistry",
    "MarketSnapshot",
    "NewsItem",
    "PeerCompany",
    "ProviderConfigError",
    "ProviderSelection",
    "REQUIRED_DCF_INPUT_RANGES",
    "ResearchPacket",
    "ResearchProviderSelection",
    "ResearchService",
    "RatesSnapshot",
    "ToolSpec",
    "TranscriptSignal",
    "TsmSnapshot",
    "build_phase_v1_tool_registry",
    "build_data_service",
    "build_research_service",
]
