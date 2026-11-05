"""Value object for the campaign seat limit."""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_MAX_SEATS = 6
MIN_MAX_SEATS = 2
MAX_MAX_SEATS = 20


class InvalidMaxSeats(ValueError):
    """Raised when a seat limit violates the campaign rules."""


@dataclass(frozen=True, slots=True)
class MaxSeats:
    """An integer seat limit; the organizer always occupies one seat."""

    value: int

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or not isinstance(self.value, int):
            raise InvalidMaxSeats("max_seats must be an integer")
        if not MIN_MAX_SEATS <= self.value <= MAX_MAX_SEATS:
            raise InvalidMaxSeats(f"max_seats must be between {MIN_MAX_SEATS} and {MAX_MAX_SEATS}")

    @classmethod
    def default(cls) -> MaxSeats:
        return cls(value=DEFAULT_MAX_SEATS)
