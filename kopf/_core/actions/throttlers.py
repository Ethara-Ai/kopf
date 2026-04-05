import asyncio
import contextlib
import dataclasses
from collections.abc import AsyncGenerator, Iterable, Iterator

from kopf._cogs.aiokits import aiotime
from kopf._cogs.helpers import typedefs


@dataclasses.dataclass(frozen=False)
class Throttler:
    """ A state of throttling for one specific purpose (there can be a few). """
    source_of_delays: Iterator[float] | None = None
    last_used_delay: float | None = None
    active_until: float | None = None  # internal clock


@contextlib.asynccontextmanager
async def throttled(
        *,
        throttler: Throttler,
        delays: Iterable[float],
        wakeup: asyncio.Event | None = None,
        logger: typedefs.Logger,
        errors: type[BaseException] | tuple[type[BaseException], ...] = Exception,
) -> AsyncGenerator[bool, None]:
    """
    A helper to throttle any arbitrary operation.
    """
    pass
