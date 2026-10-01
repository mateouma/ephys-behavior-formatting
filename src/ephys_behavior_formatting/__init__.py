"""Formatting pipeline for Neuropixels/Plexon ephys and behavioral/trial data."""

from .aligned import AlignedSpikes
from .neuropixels import NeuropixelsExperiment
from .plexon import PlexonExperiment, PlexonSessionProcessor
from .units import Unit, UnitCriteria

__version__ = "0.1.0"

__all__ = [
    "AlignedSpikes",
    "NeuropixelsExperiment",
    "PlexonExperiment",
    "PlexonSessionProcessor",
    "Unit",
    "UnitCriteria",
]
