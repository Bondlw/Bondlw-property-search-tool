"""Abstract base class for all property portal scrapers."""

from abc import ABC, abstractmethod

from ..storage.models import RawListing


class BaseScraper(ABC):
    """Base class defining the interface for portal scrapers."""

    @abstractmethod
    def search(self, area_config: dict, budget_config: dict) -> list[RawListing]:
        """Execute search for an area and return raw listings."""

    @abstractmethod
    def get_listing_detail(self, url: str) -> RawListing | None:
        """Fetch full detail for a single listing URL."""

    @abstractmethod
    def get_portal_name(self) -> str:
        """Return the portal name (e.g., 'rightmove')."""
