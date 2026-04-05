"""
A few simple lifecycles for the handlers.

New lifecycles can be implemented the same way: accept ``handlers``
in the order they are registered (except those already succeeded),
and return the list of handlers in the order and amount to be executed.

The default behaviour of the framework is the most simplistic:
execute in the order they are registered, one by one.
"""

import logging
import random
from collections.abc import Sequence
from typing import Any

from kopf._core.actions import execution

logger = logging.getLogger(__name__)

Handlers = Sequence[execution.Handler]


def all_at_once(handlers: Handlers, **_: Any) -> Handlers:
    """Execute all handlers at once, in one event reaction cycle, if possible."""
    pass


def one_by_one(handlers: Handlers, **_: Any) -> Handlers:
    """Execute handlers one at a time, in the order they were registered."""
    pass


def randomized(handlers: Handlers, **_: Any) -> Handlers:
    """Execute one handler at a time, in the random order."""
    pass


def shuffled(handlers: Handlers, **_: Any) -> Handlers:
    """Execute all handlers at once, but in the random order."""
    pass


def asap(handlers: Handlers, *, state: execution.State, **_: Any) -> Handlers:
    """Execute one handler at a time, skip on failure, try the next one, retry after the full cycle."""
    pass


_default_lifecycle: execution.LifeCycleFn = asap


def get_default_lifecycle() -> execution.LifeCycleFn:
    return _default_lifecycle


def set_default_lifecycle(lifecycle: execution.LifeCycleFn | None) -> None:
    pass
