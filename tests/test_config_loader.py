"""Tests for config_loader validation."""

import copy

import pytest

from src.config_loader import ConfigValidationError, validate_config


@pytest.fixture
def valid_config(base_config):
    """Return a full valid config from the shared base_config fixture."""
    return copy.deepcopy(base_config)


class TestValidateConfig:
    """Tests for the validate_config function."""

    def test_valid_config_returns_no_warnings(self, valid_config):
        warnings = validate_config(valid_config)
        assert warnings == []

    def test_missing_required_section_raises(self, valid_config):
        del valid_config["user"]
        with pytest.raises(ConfigValidationError, match="Missing required section.*user"):
            validate_config(valid_config)

    def test_section_not_a_dict_raises(self, valid_config):
        valid_config["user"] = "not-a-dict"
        with pytest.raises(ConfigValidationError, match="must be a mapping"):
            validate_config(valid_config)

    def test_missing_required_key_raises(self, valid_config):
        del valid_config["user"]["deposit"]
        with pytest.raises(ConfigValidationError, match="Missing required key.*user.deposit"):
            validate_config(valid_config)

    def test_invalid_type_raises(self, valid_config):
        valid_config["user"]["mortgage_term_years"] = "thirty"
        with pytest.raises(ConfigValidationError, match="Invalid type.*mortgage_term_years"):
            validate_config(valid_config)

    def test_budget_key_missing_raises(self, valid_config):
        del valid_config["budget"]["freehold"]
        with pytest.raises(ConfigValidationError, match="Missing required key.*budget.freehold"):
            validate_config(valid_config)

    def test_numeric_out_of_range_returns_warning(self, valid_config):
        valid_config["user"]["annual_income"] = 5000  # below 10_000 min
        warnings = validate_config(valid_config)
        assert any("annual_income" in w and "outside expected range" in w for w in warnings)

    def test_monthly_target_min_exceeds_max_raises(self, valid_config):
        valid_config["monthly_target"]["min"] = 1000
        valid_config["monthly_target"]["max"] = 500
        with pytest.raises(ConfigValidationError, match="monthly_target.min.*exceeds.*monthly_target.max"):
            validate_config(valid_config)

    def test_scoring_weights_not_100_returns_warning(self, valid_config):
        valid_config["scoring"]["financial_fit"] = 50  # sum now 120 instead of 100
        warnings = validate_config(valid_config)
        assert any("Scoring weights sum to" in w for w in warnings)

    def test_scoring_weights_sum_to_100_no_warning(self, valid_config):
        warnings = validate_config(valid_config)
        assert not any("Scoring weights" in w for w in warnings)

    def test_multiple_missing_sections_reported(self, valid_config):
        del valid_config["user"]
        del valid_config["scoring"]
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_config(valid_config)
        message = str(exc_info.value)
        assert "user" in message
        assert "scoring" in message

    def test_hard_gates_type_validation(self, valid_config):
        valid_config["hard_gates"]["min_bedrooms"] = 1.5  # should be int
        with pytest.raises(ConfigValidationError, match="Invalid type.*min_bedrooms"):
            validate_config(valid_config)

    def test_mortgage_rate_out_of_range_warning(self, valid_config):
        valid_config["user"]["mortgage_rate"] = 20.0  # above 15.0 max
        warnings = validate_config(valid_config)
        assert any("mortgage_rate" in w for w in warnings)

    def test_deposit_zero_is_valid(self, valid_config):
        valid_config["user"]["deposit"] = 0
        warnings = validate_config(valid_config)
        # Should not raise, 0 is within range [0, 1_000_000]
        assert isinstance(warnings, list)
