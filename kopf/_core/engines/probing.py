import asyncio
import datetime
import logging
import urllib.parse

import aiohttp.web

from kopf._cogs.configs import configuration
from kopf._cogs.structs import ephemera, ids
from kopf._core.actions import execution, lifecycles
from kopf._core.engines import activities
from kopf._core.intents import causes, registries

logger = logging.getLogger(__name__)

LOCALHOST: str = 'localhost'
HTTP_PORT: int = 80


async def health_reporter(
        endpoint: str,
        *,
        memo: ephemera.AnyMemo,
        indices: ephemera.Indices,
        registry: registries.OperatorRegistry,
        settings: configuration.OperatorSettings,
        ready_flag: asyncio.Event | None = None,  # used for testing
) -> None:
    """
    Simple HTTP(S)/TCP server to report the operator's health to K8s probes.

    Runs forever until cancelled (which happens if any other root task
    is cancelled or fails). Once it stops responding for any reason,
    Kubernetes will assume the pod is not alive anymore, and will restart it.
    """
    probing_container: dict[ids.HandlerId, execution.Result] = {}
    probing_timestamp: datetime.datetime | None = None
    probing_max_age = datetime.timedelta(seconds=10.0)
    probing_lock = asyncio.Lock()


    parts = urllib.parse.urlsplit(endpoint)
    if parts.scheme == 'http':
        host = parts.hostname or LOCALHOST
        port = parts.port or HTTP_PORT
        path = parts.path
    else:
        raise Exception(f"Unsupported scheme: {endpoint}")

    app = aiohttp.web.Application()
    app.add_routes([aiohttp.web.get(path, get_health)])

    runner = aiohttp.web.AppRunner(app, handle_signals=False, shutdown_timeout=1.0)
    await runner.setup()

    site = aiohttp.web.TCPSite(runner, host, port)
    await site.start()

    # Log with the actual URL: normalised, with hostname/port set.
    url = urllib.parse.urlunsplit([parts.scheme, f'{host}:{port}', path, '', ''])
    logger.debug(f"Serving health status at {url}")
    if ready_flag is not None:
        ready_flag.set()

    try:
        # Sleep forever. No activity is needed.
        await asyncio.Event().wait()
    finally:
        # On any reason of exit, stop reporting the health.
        await asyncio.shield(runner.cleanup())
