"""HTTP-boundary configuration for guest identity (origins, cookies)."""

from __future__ import annotations

from dataclasses import dataclass

from dunvyr.identity.public import SESSION_COOKIE_NAME

DEFAULT_ALLOWED_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)

_TRUTHY = {"1", "true", "yes", "on"}

__all__ = [
    "DEFAULT_ALLOWED_ORIGINS",
    "SESSION_COOKIE_NAME",
    "AllowedOrigins",
    "env_flag",
]


def env_flag(raw: str | None) -> bool:
    """Parse an opt-in environment flag; only explicit truthy values count."""
    return raw is not None and raw.strip().lower() in _TRUTHY


@dataclass(frozen=True, slots=True)
class AllowedOrigins:
    origins: tuple[str, ...]

    @classmethod
    def parse(cls, raw: str | None) -> AllowedOrigins:
        if raw is None:
            return cls(origins=DEFAULT_ALLOWED_ORIGINS)
        parsed = tuple(part.strip() for part in raw.split(",") if part.strip())
        return cls(origins=parsed or DEFAULT_ALLOWED_ORIGINS)

    def contains(self, origin: str) -> bool:
        return origin in self.origins
