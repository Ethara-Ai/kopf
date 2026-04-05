"""
All the functions to manipulate the object finalization and deletion.

Finalizers are used to block the actual deletion until the finalizers
are removed, meaning that the operator has done all its duties
to "release" the object (e.g. cleanups; delete-handlers in our case).
"""

from kopf._cogs.structs import bodies, patches


def is_deletion_ongoing(body: bodies.RawBody) -> bool:
    pass


def is_deletion_blocked(body: bodies.RawBody, finalizer: str) -> bool:
    pass


def block_deletion(body: bodies.RawBody, finalizer: str) -> None:
    pass


def allow_deletion(body: bodies.RawBody, finalizer: str) -> None:
    pass
