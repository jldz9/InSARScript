from abc import ABC, abstractmethod
from typing import List, Union, Optional, Any, Type

class BaseDownloader(ABC):
    name: str
    default_config: Optional[Type] = None

    def __init__(self, config=None):
        if config is None and self.default_config:
            self.config = self.default_config()
        else:
            self.config = config

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        from .registry import Downloader
        if hasattr(cls, "name") and cls.name:
            Downloader.register(cls)

    @abstractmethod
    def search(self) -> Any:
        pass

    @abstractmethod
    def download(self) -> Any:
        pass

class ISCEProcessor(ABC):
    name: str
    default_config: Optional[Type] = None

    def __init__(self, config=None):
        if config is None and self.default_config:
            self.config = self.default_config()
        else:
            self.config = config

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # 1. Handle Registration (The Recruiter)
        from .registry import Processor
        if hasattr(cls, "name") and cls.name:
            Processor.register(cls)

    @abstractmethod
    def run(self) -> Any:
        pass

class Hyp3Processor(ABC):
    name: str
    default_config: Optional[Type] = None

    def __init__(self, config=None):
        if config is None and self.default_config:
            self.config = self.default_config()
        else:
            self.config = config

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # 1. Handle Registration (The Recruiter)
        from .registry import Processor
        if hasattr(cls, "name") and cls.name:
            Processor.register(cls)

    @abstractmethod
    def submit(self) -> Any:
        pass

class BaseAnalysis(ABC):
    name: str
    default_config: Optional[Type] = None
    def __init__(self, config=None):
        if config is None and self.default_config:
            self.config = self.default_config()
        else:
            self.config = config

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # 1. Handle Registration (The Recruiter)
        from .registry import Analyzer
        if hasattr(cls, "name") and cls.name:
            Analyzer.register(cls)

    @abstractmethod
    def run(self) -> Any:
        pass