from typing import Protocol

from campus.models import ProviderResult


class Provider(Protocol):
    name: str

    def sync(self) -> ProviderResult: ...

    def check(self) -> ProviderResult: ...
