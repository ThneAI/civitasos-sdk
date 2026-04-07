"""CivitasOS Framework Adapters — bridge external agent frameworks into CivitasOS."""

from adapters.langchain_adapter import CivitasLangChainAgent
from adapters.crewai_adapter import CivitasCrewAgent

__all__ = ["CivitasLangChainAgent", "CivitasCrewAgent"]
