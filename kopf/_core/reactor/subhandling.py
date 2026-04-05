import collections.abc
import contextlib
from collections.abc import AsyncIterator, Iterable
from contextvars import ContextVar

from kopf._cogs.configs import configuration
from kopf._cogs.structs import ids
from kopf._core.actions import execution, invocation, lifecycles, progression
from kopf._core.intents import callbacks, causes, handlers as handlers_, registries

# The task-local context; propagated down the stack instead of multiple kwargs.
# Used in `@kopf.subhandler` and `kopf.execute()` to add/get the sub-handlers.
subregistry_var: ContextVar[registries.ChangingRegistry] = ContextVar('subregistry_var')
subexecuted_var: ContextVar[bool] = ContextVar('subexecuted_var')




async def execute(
        *,
        fns: Iterable[callbacks.ChangingFn] | None = None,
        handlers: Iterable[handlers_.ChangingHandler] | None = None,
        registry: registries.ChangingRegistry | None = None,
        lifecycle: execution.LifeCycleFn | None = None,
        cause: execution.Cause | None = None,
) -> None:
    """
    Execute the handlers in an isolated lifecycle.

    This function is a public entry point with multiple ways to specify
    the handlers: either as the raw functions, or as the pre-created handlers,
    or as a registry (as used in the object handling).

    If no explicit functions or handlers or registry are passed,
    the sub-handlers of the current handler are assumed, as accumulated
    in the per-handler registry with ``@kopf.subhandler``.

    If the call to this method for the sub-handlers is not done explicitly
    in the handler, it is done implicitly after the handler is exited.
    One way or another, it is executed for the sub-handlers.
    """
    pass
