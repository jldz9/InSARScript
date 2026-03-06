import dataclasses
from copy import deepcopy

class Registry:
    def __init__(self):
        self._registry = {}

    def register(self, cls):
        self._registry[cls.name] = cls
        return cls

    def create(self, name, config=None, **overrides):
        if name not in self._registry:
            raise ValueError(f"{name} not registered")
        cls = self._registry[name]

        if config is not None:
            final_config = deepcopy(config)
        elif hasattr(cls, "default_config"):
            final_config = cls.default_config()
        else:
            final_config = {}

        if overrides:
            if dataclasses.is_dataclass(final_config):
                try:
                    final_config = dataclasses.replace(final_config, **overrides)
                except TypeError as e:
                    raise ValueError(f"Invalid override parameters: {e}")   
            elif isinstance(final_config, dict):
                final_config.update(overrides)
            else:   
                for key, value in overrides.items():
                    if hasattr(final_config, key):
                        setattr(final_config, key, value)
                    else:
                        raise AttributeError(f"'{type(final_config).__name__}' has no field '{key}'")
        return cls(final_config)

    def available(self):
        return list(self._registry.keys())


Downloader = Registry()
Processor = Registry()
Analyzer = Registry()