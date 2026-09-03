"""Shared test fixtures.

Points the application at a deterministic synthetic energy dataset via the CSV
path environment overrides so the whole suite runs without the personal,
uncommitted CSV inputs. Tests that pass explicit paths to the data loader are
unaffected.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from sample_data import write_sample_energy_csvs  # noqa: E402


@pytest.fixture(scope="session")
def sample_energy_csvs(tmp_path_factory) -> tuple[Path, Path]:
    directory = tmp_path_factory.mktemp("energy-data")
    utility_path = directory / "combined-electric-usage.csv"
    solar_path = directory / "combined-monthly-energy.csv"
    write_sample_energy_csvs(utility_path, solar_path)
    return utility_path, solar_path


@pytest.fixture(autouse=True)
def use_sample_energy_csvs(sample_energy_csvs, monkeypatch) -> None:
    utility_path, solar_path = sample_energy_csvs
    monkeypatch.setenv("HOME_ENERGY_MODEL_UTILITY_CSV", str(utility_path))
    monkeypatch.setenv("HOME_ENERGY_MODEL_SOLAR_CSV", str(solar_path))
