"""Live machine simulator (testing / demo).

Generates realistic 30-second data for every machine, feeds it through the same
ingestion ports a real machine would use, and re-runs the analysis each tick.
"""

from senseminds.simulation.generator import Drift, MachineGenerator
from senseminds.simulation.live import LiveSimulator, SimulatorConfig
from senseminds.simulation.profiles import SensorProfile, profile_unit

__all__ = [
    "Drift",
    "LiveSimulator",
    "MachineGenerator",
    "SensorProfile",
    "SimulatorConfig",
    "profile_unit",
]
