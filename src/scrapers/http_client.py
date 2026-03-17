"""Shared HTTP client with rate limiting, retry logic, and UA rotation."""

import logging
import random
import time
from pathlib import Path

import requests

logger = logging.getLogger(__name__)


class ListingGoneError(Exception):
    """Raised when a listing returns HTTP 410 Gone (removed from portal)."""


class HttpClient:
    """HTTP session with rate limiting, retry logic, and user agent rotation."""

    BOT_BLOCK_MARKERS = [
        "captcha", "robot", "blocked", "access denied",
        "please verify", "security check", "challenge",
    ]

    def __init__(self, config: dict):
        self.session = requests.Session()
        self.min_delay = config.get("scraping", {}).get("min_delay_seconds", 2)
        self.max_delay = config.get("scraping", {}).get("max_delay_seconds", 5)
        self.max_retries = config.get("scraping", {}).get("max_retries", 3)
        self.ua_pool = self._load_user_agents()
        self._last_request_time = 0

    def _load_user_agents(self) -> list[str]:
        """Load user agent strings from pool file."""
        ua_file = Path("config/user_agent_pool.txt")
        if ua_file.exists():
            agents = [
                line.strip()
                for line in ua_file.read_text().splitlines()
                if line.strip()
            ]
            if agents:
                return agents
        # Fallback
        return [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ]

    def _rate_limit(self):
        """Enforce delay between requests."""
        elapsed = time.time() - self._last_request_time
        delay = random.uniform(self.min_delay, self.max_delay)
        if elapsed < delay:
            time.sleep(delay - elapsed)
        self._last_request_time = time.time()

    def _get_headers(self) -> dict:
        """Generate browser-like headers with a random user agent."""
        return {
            "User-Agent": random.choice(self.ua_pool),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-GB,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
        }

    def _is_bot_blocked(self, response: requests.Response) -> bool:
        """Check if the response indicates bot detection."""
        if response.status_code in (403, 429, 503):
            return True
        content_lower = response.text[:2000].lower()
        return any(marker in content_lower for marker in self.BOT_BLOCK_MARKERS)

    def get(self, url: str) -> requests.Response | None:
        """Fetch a URL with rate limiting and retry."""
        for attempt in range(self.max_retries):
            self._rate_limit()
            try:
                response = self.session.get(
                    url, headers=self._get_headers(), timeout=30
                )

                if self._is_bot_blocked(response):
                    wait = (attempt + 1) * 10
                    logger.warning(
                        f"Bot block detected on attempt {attempt + 1} for {url}. "
                        f"Waiting {wait}s before retry."
                    )
                    time.sleep(wait)
                    continue

                if response.status_code == 410:
                    raise ListingGoneError(
                        f"Listing removed (410 Gone): {url}"
                    )

                response.raise_for_status()
                return response

            except requests.RequestException as e:
                logger.warning(f"Request failed (attempt {attempt + 1}): {e}")
                if attempt < self.max_retries - 1:
                    time.sleep((attempt + 1) * 5)

        logger.error(f"All {self.max_retries} attempts failed for {url}")
        return None

    def get_text(self, url: str) -> str | None:
        """Fetch URL and return text content."""
        response = self.get(url)
        return response.text if response else None
