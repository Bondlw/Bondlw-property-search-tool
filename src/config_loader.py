"""Load and validate the search configuration."""

import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path("config/search_config.yaml")

# Required top-level sections
_REQUIRED_SECTIONS = ("user", "budget", "monthly_target", "hard_gates", "scoring")

# Required keys within each section, with expected type
_REQUIRED_KEYS = {
    "user": {
        "annual_income": (int, float),
        "monthly_take_home": (int, float),
        "deposit": (int, float),
        "mortgage_rate": (int, float),
        "mortgage_term_years": int,
    },
    "budget": {
        "freehold": dict,
        "leasehold": dict,
    },
    "monthly_target": {
        "min": (int, float),
        "max": (int, float),
    },
    "hard_gates": {
        "min_bedrooms": int,
        "lease_minimum_years": int,
        "service_charge_max_pa": (int, float),
        "ground_rent_max_pa": (int, float),
    },
    "scoring": {
        "financial_fit": (int, float),
        "crime_safety": (int, float),
        "cost_predictability": (int, float),
        "layout_livability": (int, float),
        "walkability": (int, float),
        "long_term_flexibility": (int, float),
    },
}

# Numeric range constraints: (section, key, min_val, max_val)
_RANGE_CONSTRAINTS = [
    ("user", "annual_income", 10_000, 500_000),
    ("user", "monthly_take_home", 500, 50_000),
    ("user", "deposit", 0, 1_000_000),
    ("user", "mortgage_rate", 0.5, 15.0),
    ("user", "mortgage_term_years", 5, 40),
    ("monthly_target", "min", 100, 10_000),
    ("monthly_target", "max", 100, 10_000),
    ("hard_gates", "min_bedrooms", 1, 10),
    ("hard_gates", "lease_minimum_years", 1, 999),
    ("hard_gates", "service_charge_max_pa", 0, 20_000),
    ("hard_gates", "ground_rent_max_pa", 0, 10_000),
]


class ConfigValidationError(Exception):
    """Raised when the configuration fails validation."""


def validate_config(config: dict) -> list[str]:
    """Validate config structure, types, and ranges.

    Returns a list of warning strings (non-fatal).
    Raises ConfigValidationError for missing required keys or invalid types.
    """
    errors = []
    warnings = []

    # Check required sections
    for section in _REQUIRED_SECTIONS:
        if section not in config:
            errors.append(f"Missing required section: '{section}'")
        elif not isinstance(config[section], dict):
            errors.append(f"Section '{section}' must be a mapping, got {type(config[section]).__name__}")

    if errors:
        raise ConfigValidationError(
            "Config validation failed:\n  " + "\n  ".join(errors)
        )

    # Check required keys and types within sections
    for section, keys in _REQUIRED_KEYS.items():
        section_data = config.get(section, {})
        for key, expected_type in keys.items():
            if key not in section_data:
                errors.append(f"Missing required key: {section}.{key}")
                continue
            value = section_data[key]
            if not isinstance(value, expected_type):
                errors.append(
                    f"Invalid type for {section}.{key}: "
                    f"expected {expected_type}, got {type(value).__name__} ({value!r})"
                )

    if errors:
        raise ConfigValidationError(
            "Config validation failed:\n  " + "\n  ".join(errors)
        )

    # Range validation (warnings for out-of-range, errors for nonsensical)
    for section, key, min_val, max_val in _RANGE_CONSTRAINTS:
        value = config.get(section, {}).get(key)
        if value is None:
            continue
        if not isinstance(value, (int, float)):
            continue
        if value < min_val or value > max_val:
            warnings.append(
                f"{section}.{key} = {value} is outside expected range [{min_val}, {max_val}]"
            )

    # Cross-field validation
    monthly_min = config.get("monthly_target", {}).get("min", 0)
    monthly_max = config.get("monthly_target", {}).get("max", 0)
    if monthly_min > monthly_max:
        errors.append(
            f"monthly_target.min ({monthly_min}) exceeds monthly_target.max ({monthly_max})"
        )

    # Scoring weights should sum to ~100
    scoring = config.get("scoring", {})
    total_weight = sum(v for v in scoring.values() if isinstance(v, (int, float)))
    if total_weight != 100:
        warnings.append(f"Scoring weights sum to {total_weight}, expected 100")

    if errors:
        raise ConfigValidationError(
            "Config validation failed:\n  " + "\n  ".join(errors)
        )

    return warnings


def load_config(config_path: Path | str = DEFAULT_CONFIG_PATH) -> dict:
    """Load and validate the YAML configuration file."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    if config is None:
        raise ValueError(f"Config file is empty: {path}")

    warnings = validate_config(config)
    for warning in warnings:
        logger.warning(f"Config warning: {warning}")

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
