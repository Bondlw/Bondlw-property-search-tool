"""Load and validate the search configuration."""

from pathlib import Path

import yaml


DEFAULT_CONFIG_PATH = Path("config/search_config.yaml")


def load_config(config_path: Path | str = DEFAULT_CONFIG_PATH) -> dict:
    """Load the YAML configuration file."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    if config is None:
        raise ValueError(f"Config file is empty: {path}")

    return config


def get_all_areas(config: dict) -> list[dict]:
    """Get all active search areas from config."""
    areas = []
    for area_type in ("primary", "secondary"):
        for area in config.get("search_areas", {}).get(area_type, []):
            area["area_type"] = area_type
            areas.append(area)
    return areas


def get_areas_by_type(config: dict, area_type: str) -> list[dict]:
    """Get search areas of a specific type."""
    areas = config.get("search_areas", {}).get(area_type, [])
    for area in areas:
        area["area_type"] = area_type
    return areas
