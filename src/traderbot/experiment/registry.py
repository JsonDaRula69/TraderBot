from traderbot.experiment.shared import TreatmentInterface

_registry: dict[str, type] = {}


def discover_treatments() -> dict[str, type]:
    from traderbot.experiment import treatments

    registry = getattr(treatments, "TREATMENT_REGISTRY", [])
    discovered: dict[str, type] = {}
    for cls in registry:
        if not issubclass(cls, TreatmentInterface):
            raise TypeError(f"Treatment {cls.__name__} must subclass TreatmentInterface")
        discovered[cls.__name__] = cls
    return discovered


def register_treatment(name: str, cls: type) -> None:
    _registry[name] = cls


def get_treatment(name: str) -> type | None:
    return _registry.get(name)


def list_treatments() -> list[str]:
    return sorted(_registry.keys())
