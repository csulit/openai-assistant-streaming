from typing import Dict, Any, Protocol, runtime_checkable
from abc import ABC, abstractmethod
import logging

logger = logging.getLogger(__name__)


@runtime_checkable
class AssistantTool(Protocol):
    """Protocol for assistant tools"""

    @property
    def name(self) -> str:
        """Name of the tool"""
        ...

    def get_function_definition(self) -> Dict[str, Any]:
        """Get OpenAI function definition"""
        ...


class BaseAssistantTool(ABC):
    """Base class for assistant tools"""

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the tool"""
        pass

    @abstractmethod
    def get_function_definition(self) -> Dict[str, Any]:
        """Get OpenAI function definition"""
        pass
