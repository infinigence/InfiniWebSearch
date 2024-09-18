from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class BaseAction(ABC):
    @property
    @abstractmethod
    def function_defination(self) -> Optional[Dict]:
        pass

    @abstractmethod
    def run(self, arguments: Dict) -> Any:
        pass
