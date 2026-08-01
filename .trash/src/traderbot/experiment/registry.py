import logging

from traderbot.experiment.shared import TreatmentInterface

logger = logging.getLogger(__name__)

_registry: dict[str, type] = {}


def discover_treatments() -> dict[str, type]:
    from traderbot.experiment import treatments

    registry = getattr(treatments, "TREATMENT_REGISTRY", [])
    discovered: dict[str, type] = {}
    for cls in registry:
        if not issubclass(cls, TreatmentInterface):
            raise TypeError(f"Treatment {cls.__name__} must subclass TreatmentInterface")
        discovered[cls.__name__] = cls
    logger.info("Discovered %d treatments: %s", len(discovered), list(discovered.keys()))
    return discovered


def register_treatment(name: str, cls: type) -> None:
    if name in _registry:
        logger.warning("Duplicate registration: treatment %s already registered", name)
    _registry[name] = cls
    logger.info("Registered treatment %s -> %s", name, cls.__name__)


def get_treatment(name: str) -> type | None:
    return _registry.get(name)


def list_treatments() -> list[str]:
    return sorted(_registry.keys())
