"""The provider cannot access gameplay, identities, scenario IDs or repositories."""

from typing import Protocol


class NarrationModel(Protocol):
    async def generate(self, success: bool, facts: tuple[str, ...]) -> str: ...
