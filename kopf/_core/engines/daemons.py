"""
Daemons are background tasks accompanying the individual resource objects.

Every ``@kopf.daemon`` and ``@kopf.timer`` handler produces a separate
asyncio task to either directly execute the daemon, or to trigger one-shot
handlers by schedule. The wrapping tasks are always async; the sync functions
are called in thread executors as part of a regular handler invocation.

These tasks are remembered in the per-resources *memories* (arbitrary data
containers) throughout the lifecycle of the operator.

Since the operators are event-driven conceptually, there are no background tasks
running for every individual resource normally (i.e. without the daemons),
and there are no connectors between the operator's root tasks and the daemons,
so there is no way to stop/kill/cancel the daemons when the operator exits.

For this, there is an artificial root task spawned to kill all the daemons
when the operator exits, and all root tasks are terminated.
Otherwise, all the daemons would be considered as "hung" tasks and would be
forcefully killed after some timeout --- which can be avoided,
since we are aware of the daemons, and they are not actually "hung".
"""
import abc
import asyncio
import dataclasses
import sys
import warnings
from collections.abc import Collection, Iterable, MutableMapping, Sequence

from kopf._cogs.aiokits import aiotasks, aiotime, aiotoggles
from kopf._cogs.configs import configuration
from kopf._cogs.helpers import typedefs
from kopf._cogs.structs import bodies, ids, patches
from kopf._core.actions import application, execution, lifecycles, loggers, progression
from kopf._core.intents import causes, handlers as handlers_, stoppers




@dataclasses.dataclass(frozen=True)
class Daemon:
    task: aiotasks.Task  # a guarding task of the daemon.
    logger: typedefs.Logger
    handler: handlers_.SpawningHandler
    stopper: stoppers.DaemonStopper  # a signaller for the termination and its reason.


@dataclasses.dataclass(frozen=False)
class DaemonsMemory:
    # For background and timed threads/tasks (invoked with the kwargs of the last-seen body).
    live_fresh_body: bodies.Body | None = None
    idle_reset_time: float = dataclasses.field(default_factory=_loop_time)
    forever_stopped: set[ids.HandlerId] = dataclasses.field(default_factory=set)
    running_daemons: dict[ids.HandlerId, Daemon] = dataclasses.field(default_factory=dict)


class DaemonsMemoriesIterator(metaclass=abc.ABCMeta):
    """
    Re-iterable view of all the running daemons for the :func:`daemon_killer`.

    Implemented in :class:`Memories`. A clean hack to resolve circular imports
    (the daemon killer needs memories, but the memories contain Daemon records)
    by splitting the specialised interface (this class) from the implementation.
    """
    @abc.abstractmethod
    def iter_all_daemon_memories(self) -> Iterable[DaemonsMemory]:
        raise NotImplementedError


async def spawn_daemons(
        *,
        settings: configuration.OperatorSettings,
        handlers: Sequence[handlers_.SpawningHandler],
        daemons: dict[ids.HandlerId, Daemon],
        cause: causes.SpawningCause,
        memory: DaemonsMemory,
) -> Collection[float]:
    """
    Ensure that all daemons are spawned for this individual resource.

    This function can be called multiple times on multiple handling cycles
    (though usually should be called on the first-seen occasion), so it must
    be idempotent: not having duplicating side-effects on multiple calls.
    """
    pass


async def match_daemons(
        *,
        settings: configuration.OperatorSettings,
        handlers: Sequence[handlers_.SpawningHandler],
        daemons: dict[ids.HandlerId, Daemon],
) -> Collection[float]:
    """
    Re-match the running daemons with the filters, and stop those mismatching.

    Stopping can take a few iterations, same as :func:`stop_daemons` would do.
    """
    pass


async def pause_daemons(
        *,
        settings: configuration.OperatorSettings,
        daemons: dict[ids.HandlerId, Daemon],
        operator_paused: aiotoggles.ToggleSet | None,  # None for tests
) -> Collection[float]:
    """
    Re-check the desired state of daemons according to the operator's state.

    There is a glitch in the daemon orchestration (e.g., with 3+ pods in #1266):

    If the operator is paused, the watcher() can still produce some events
    before being stopped. The watcher() spawns a worker(). The worker() calls
    the processor(). The process_resource_event() calls the spawn_daemons().
    The spawn_daemons() creates new daemons with the `stopper` set to "off"
    and registers them in memories. It all takes time.

    Meanwhile, once the operator is paused, the daemon_killer()
    kills the daemons it knows to the moment, which excludes the daemons
    that will be spawned a few moments later in the flow described above.

    There is no good synchronization primitive to protect against this case
    without syncing all resources, breaking the async nature of the operator.

    The only remedy is to let such daemons spawn, but trigger their stop flags
    after (strictly after!) they register themselves to the memories
    in spawn_daemons() and become exposed to the daemon killer.

    This routine does exactly that: stops newly spawned daemons.
    """
    pass


async def stop_daemons(
        *,
        settings: configuration.OperatorSettings,
        daemons: dict[ids.HandlerId, Daemon],
        reason: stoppers.DaemonStoppingReason = stoppers.DaemonStoppingReason.RESOURCE_DELETED,
) -> Collection[float]:
    """
    Terminate all daemons of an individual resource (gracefully and by force).

    All daemons are terminated in parallel to speed up the termination
    (especially taking into account that some daemons can take time to finish).

    The daemons are asked to terminate as soon as the object is marked
    for deletion. It can take some time until the deletion handlers also
    finish their work. The object is not physically deleted until all
    the daemons are terminated (by putting a finalizer on it).

    **Notes on this non-trivial implementation:**

    There is a same-purpose function :func:`stop_daemon`, which works fully
    in-memory. That method is used when killing the daemons on operator exit.
    This method is used when the resource is deleted.

    The difference is that in this method (termination with delays and patches),
    other on-deletion handlers can be happening at the same time as the daemons
    are being terminated (it can take time due to backoffs and timeouts).
    In the end, the finalizer should be removed only once all deletion handlers
    have succeeded and all daemons are terminated --- not earlier than that.
    None of this (handlers and finalizers) is needed for the operator exiting.

    To know "when" the next check of daemons should be performed:

    * EITHER the operator should block this resource's processing and wait until
      the daemons are terminated --- thus leaking daemon's abstractions and
      logic and tools (e.g. a task scheduler) to the upper level of processing;

    * OR the daemons termination should mimic the change-detection handlers
      and simulate the delays with multiple handling cycles --- in order to
      re-check the daemon's status regularly until they are done.

    Both of these approaches have the same complexity. But the latter one
    keeps the logic isolated in the daemons module/routines (a bit cleaner).

    Hence, these duplicate methods of termination for different cases
    (as by their surrounding circumstances: deletion handlers and finalizers).
    """
    pass


async def daemon_killer(
        *,
        settings: configuration.OperatorSettings,
        memories: DaemonsMemoriesIterator,
        operator_paused: aiotoggles.ToggleSet,
) -> None:
    """
    An operator's root task to kill the daemons on the operator's demand.

    The "demand" comes in two cases: when the operator is exiting (gracefully
    or not), and when the operator is pausing because of peering. In that case,
    all watch-streams are disconnected, and all daemons/timers should stop.

    When pausing, the daemons/timers are stopped via their regular stopping
    procedure: with graceful or forced termination, backoffs, timeouts.

    .. warning::

        Each daemon will be respawned on the next K8s watch-event strictly
        after the previous daemon is fully stopped.
        There are never 2 instances of the same daemon running in parallel.

        In normal cases (enough time is given to stop), this is usually done
        by the post-pause re-listing event. In rare cases when the re-pausing
        happens faster than the daemon is stopped (highly unlikely to happen),
        that event can be missed because the daemon is being stopped yet,
        so the respawn can happen with a significant delay.

        This issue is considered low-priority & auxiliary, so as the peering
        itself. It can be fixed later. Workaround: make daemons exit fast.
    """
    # Unlimited job pool size —- the same as if we would be managing the tasks directly.
    # Unlimited timeout in `close()` -- since we have our own per-daemon timeout management.
    scheduler = aiotasks.Scheduler()
    try:
        while True:

            # Stay here while the operator is running normally, until it is paused.
            await operator_paused.wait_for(True)

            # The stopping tasks are "fire-and-forget" -- we do not get (or care of) the result.
            # The daemons remain resumable, since they exit not on their own accord.
            # From time to time, continue killing the daemons that sneak into processing queues.
            # This is a secondary safeguard against #1266: events sneaked into workers on pausing.
            # The primary safeguard is in pause_daemons(): stop daemons immediately on spawning.
            while operator_paused.is_on():
                for memory in memories.iter_all_daemon_memories():
                    for daemon in memory.running_daemons.values():
                        await scheduler.spawn(
                            name=f"pausing stopper of {daemon}",
                            coro=stop_daemon(
                                settings=settings,
                                daemon=daemon,
                                reason=stoppers.DaemonStoppingReason.OPERATOR_PAUSING))

                # Stay here while the operator is paused, until it is resumed.
                # The fresh stream of watch-events will spawn new daemons naturally.
                if sys.version_info < (3, 11):  # python 3.10 only, TODO remove in Oct'26
                    await operator_paused.wait_for(False)
                else:
                    try:
                        async with asyncio.timeout(1.0):
                            await operator_paused.wait_for(False)
                    except TimeoutError:
                        pass

    # Terminate all running daemons when the operator exits (and this task is cancelled).
    finally:
        for memory in memories.iter_all_daemon_memories():
            for daemon in memory.running_daemons.values():
                await scheduler.spawn(
                    name=f"exiting stopper of {daemon}",
                    coro=stop_daemon(
                        settings=settings,
                        daemon=daemon,
                        reason=stoppers.DaemonStoppingReason.OPERATOR_EXITING))
        await scheduler.wait()  # prevent insta-cancelling our own coros (daemon stoppers).
        await scheduler.close()


async def stop_daemon(
        *,
        settings: configuration.OperatorSettings,
        daemon: Daemon,
        reason: stoppers.DaemonStoppingReason,
) -> None:
    """
    Stop a single daemon.

    The purpose is the same as in :func:`stop_daemons`, but this function
    is called on operator exiting, so there is no multi-step handling,
    everything happens in memory and linearly (while respecting the timing).

    For explanation on different implementations, see :func:`stop_daemons`.
    """
    handler = daemon.handler
    if isinstance(handler, handlers_.DaemonHandler):
        backoff = handler.cancellation_backoff
        timeout = handler.cancellation_timeout
    elif isinstance(handler, handlers_.TimerHandler):
        backoff = None
        timeout = None
    else:
        raise RuntimeError(f"Unsupported daemon handler: {handler!r}")

    # Whatever happens with other flags & logs & timings, this flag must be surely set.
    daemon.stopper.set(reason=reason)
    await _wait_for_instant_exit(settings=settings, daemon=daemon)

    if daemon.task.done():
        daemon.logger.debug(f"{handler} has exited gracefully.")

    # Try different approaches to exiting the daemon based on timings.
    if not daemon.task.done() and backoff is not None:
        daemon.stopper.set(reason=stoppers.DaemonStoppingReason.DAEMON_SIGNALLED)
        daemon.logger.debug(f"{handler} is signalled to exit gracefully.")
        await aiotasks.wait([daemon.task], timeout=backoff)

    if not daemon.task.done() and timeout is not None:
        daemon.stopper.set(reason=stoppers.DaemonStoppingReason.DAEMON_CANCELLED)
        daemon.logger.debug(f"{handler} is signalled to exit by force.")
        daemon.task.cancel()
        await aiotasks.wait([daemon.task], timeout=timeout)

    if not daemon.task.done():
        daemon.stopper.set(reason=stoppers.DaemonStoppingReason.DAEMON_ABANDONED)
        daemon.logger.warning(f"{handler} did not exit in time. Leaving it orphaned.")
        warnings.warn(f"{handler} did not exit in time.", ResourceWarning)


async def _wait_for_instant_exit(
        *,
        settings: configuration.OperatorSettings,
        daemon: Daemon,
) -> None:
    """
    Wait for a kind-of-instant exit of a daemon/timer.

    It may be that the daemon exits instantly (if written properly).
    Avoid resource patching and unnecessary handling cycles in this case:
    just give the asyncio event loop extra time & cycles to finish it.

    There is nothing "instant", of course. Any code takes some time to execute.
    We just assume that the "instant" is something defined by a small timeout
    and a few zero-time asyncio cycles (read as: zero-time ``await`` calls).
    """

    if daemon.task.done():
        pass

    elif settings.background.instant_exit_timeout is not None:
        await aiotasks.wait([daemon.task], timeout=settings.background.instant_exit_timeout)

    elif settings.background.instant_exit_zero_time_cycles is not None:
        for _ in range(settings.background.instant_exit_zero_time_cycles):
            await asyncio.sleep(0)
            if daemon.task.done():
                break


async def _runner(
        *,
        settings: configuration.OperatorSettings,
        daemons: dict[ids.HandlerId, Daemon],
        handler: handlers_.SpawningHandler,
        memory: DaemonsMemory,
        cause: causes.DaemonCause,
) -> None:
    """
    Guard a running daemon during its life cycle.

    Synchronous daemons are awaited until they exit and postpone cancellation.
    The runner will not exit until the thread exits. See ``invoke`` for details.
    """
    pass


async def _daemon(
        *,
        settings: configuration.OperatorSettings,
        handler: handlers_.DaemonHandler,
        cause: causes.DaemonCause,
) -> None:
    """
    A long-running guarding task for a resource daemon handler.

    The handler is executed either once or repeatedly, based on the handler
    declaration.

    A few kinds of errors are suppressed, those expected from the daemons when
    they are cancelled due to the resource deletion.
    """
    pass


async def _timer(
        *,
        settings: configuration.OperatorSettings,
        handler: handlers_.TimerHandler,
        memory: DaemonsMemory,
        cause: causes.DaemonCause,
) -> None:
    """
    A long-running guarding task for resource timer handlers.

    Each individual handler for each individual k8s-object gets its own task.
    Even though asyncio can schedule the delayed execution of the callbacks
    with ``loop.call_later()`` and ``loop.call_at()``, we do not use them:

    * First, the callbacks are synchronous, making it impossible to patch
      the k8s-objects with the returned results of the handlers.

    * Second, our timers are more sophisticated: they track the last-seen time,
      obey the idle delays, and are instantly terminated/cancelled on the object
      deletion or on the operator exit.

    * Third, sharp timing would require an external timestamp storage anyway,
      which is easier to keep as a local variable inside a function.

    It is hard to implement all of this with native asyncio timers.
    It is much easier to have an extra task which mostly sleeps,
    but calls the handling functions from time to time.
    """
    pass
