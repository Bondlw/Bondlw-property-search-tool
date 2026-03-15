"""Data models for the property search tool."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RawListing:
    """Raw data extracted from a portal before enrichment."""
    portal: str
    portal_id: str
    url: str
    title: str
    price: int
    address: str
    postcode: str
    property_type: str
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    tenure: Optional[str] = None
    lease_years: Optional[int] = None
    service_charge_pa: Optional[int] = None
    ground_rent_pa: Optional[int] = None
    council_tax_band: Optional[str] = None
    epc_rating: Optional[str] = None
    description: str = ""
    key_features: list = field(default_factory=list)
    floorplan_urls: list = field(default_factory=list)
    video_url: Optional[str] = None
    brochure_url: Optional[str] = None
    rooms: list = field(default_factory=list)  # [{name, width, length, unit}]
    images: list = field(default_factory=list)
    agent_name: Optional[str] = None
    first_listed_date: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    nearest_stations: list = field(default_factory=list)  # [{name, distance_m, walk_min}]


@dataclass
class Property:
    """Full property record from the database."""
    id: int
    portal: str
    portal_id: str
    url: str
    url_normalised: str
    title: str
    price: int
    address: str
    postcode: str
    property_type: str
    bedrooms: Optional[int]
    bathrooms: Optional[int]
    tenure: Optional[str]
    lease_years: Optional[int]
    service_charge_pa: Optional[int]
    ground_rent_pa: Optional[int]
    council_tax_band: Optional[str]
    epc_rating: Optional[str]
    description: str
    key_features: str  # JSON string
    agent_name: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    first_seen_date: str
    last_seen_date: str
    first_listed_date: Optional[str]
    days_on_market: Optional[int]
    is_active: bool
    status: str
    created_at: str
    updated_at: str


@dataclass
class PriceChange:
    """A recorded price change for a property."""
    id: int
    property_id: int
    price: int
    recorded_date: str
    change_amount: Optional[int]
    change_pct: Optional[float]


@dataclass
class EnrichmentData:
    """Enrichment data for a property from external APIs."""
    property_id: int
    nearest_station_name: Optional[str] = None
    nearest_station_distance_m: Optional[float] = None
    nearest_station_walk_min: Optional[int] = None
    nearest_lidl_distance_m: Optional[float] = None
    nearest_lidl_walk_min: Optional[int] = None
    nearest_aldi_distance_m: Optional[float] = None
    nearest_aldi_walk_min: Optional[int] = None
    crime_summary: Optional[str] = None  # JSON
    crime_safety_score: Optional[float] = None
    crime_data_date: Optional[str] = None
    commute_to_london_min: Optional[int] = None
    commute_to_maidstone_min: Optional[int] = None
    annual_season_ticket: Optional[int] = None
    council_tax_band_verified: Optional[str] = None
    council_tax_annual_estimate: Optional[int] = None
    flood_zone: Optional[int] = None
    broadband_speed_mbps: Optional[float] = None
    avg_sold_price_nearby: Optional[int] = None
    enriched_at: Optional[str] = None


@dataclass
class GateResult:
    """Result of a single hard gate check."""
    gate_name: str
    passed: bool
    reason: str


@dataclass
class PropertyScore:
    """Scoring breakdown for a qualifying property."""
    property_id: int
    financial_fit: float = 0
    crime_safety: float = 0
    cost_predictability: float = 0
    layout_livability: float = 0
    walkability: float = 0
    long_term_flexibility: float = 0
    total_score: float = 0


@dataclass
class Exclusion:
    """A user-excluded property."""
    id: int
    property_id: int
    reason: str
    excluded_at: str
    excluded_by: str = "user"
