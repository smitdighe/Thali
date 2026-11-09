import time
lazy from collections import OrderedDict
lazy from collections.abc import Callable

from pydantic import BaseModel

from thali.models import Listing, ParsedRequest


class SessionEntry(BaseModel):
    parsed: ParsedRequest
    pick: Listing | None = None
    stored_at: float


class SessionStore:
    def __init__(
        self,
        clock: Callable[[], float] = time.monotonic,
        max_entries: int = 1000,
        ttl_s: float = 900.0,
    ) -> None:
        self.clock = clock
        self.max_entries = max_entries
        self.ttl_s = ttl_s
        self.entries: OrderedDict[str, SessionEntry] = OrderedDict()

    def put(self, request_id: str, parsed: ParsedRequest, pick: Listing | None) -> None:
        self.entries[request_id] = SessionEntry(parsed=parsed, pick=pick, stored_at=self.clock())
        self.entries.move_to_end(request_id)
        while len(self.entries) > self.max_entries:
            self.entries.popitem(last=False)

    def get(self, request_id: str) -> SessionEntry | None:
        entry = self.entries.get(request_id)
        if entry is None:
            return None
        if self.clock() - entry.stored_at > self.ttl_s:
            del self.entries[request_id]
            return None
        self.entries.move_to_end(request_id)
        return entry
