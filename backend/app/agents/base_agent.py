from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from app.schemas.contracts import SocketMessage

class BaseAgent(ABC):
    """
    The abstract protocol for all GenAI and Logic agents in the Chronicles Engine.
    """
    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    async def process(self, context: Dict[str, Any], message: SocketMessage) -> Optional[SocketMessage]:
        """
        Process an incoming message or state update.
        Must return a SocketMessage to broadcast, or None if it's a silent background operation.
        """
        pass