"""Run orchestration services.

Keep package exports lazy to avoid import cycles between:
- ``backend.app.skills.router`` -> ``backend.app.orchestrator.state_machine``
- ``backend.app.orchestrator.langgraph_finance_agent`` -> ``backend.app.skills.router``
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .langgraph_finance_agent import LangGraphFinanceAgent
    from .valuation_runner import ValuationRunner

__all__ = ("LangGraphFinanceAgent", "ValuationRunner")


def __getattr__(name: str) -> Any:
    if name == "LangGraphFinanceAgent":
        from .langgraph_finance_agent import LangGraphFinanceAgent

        return LangGraphFinanceAgent
    if name == "ValuationRunner":
        from .valuation_runner import ValuationRunner

        return ValuationRunner
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
