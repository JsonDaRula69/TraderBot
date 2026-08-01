"""Treatments package."""

from traderbot.experiment.treatments.calibration_bundle import CalibrationBundleTreatment
from traderbot.experiment.treatments.control import ControlTreatment

TREATMENT_REGISTRY: list[type] = [ControlTreatment, CalibrationBundleTreatment]
