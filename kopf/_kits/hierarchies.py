"""
All the functions to properly build the object hierarchies.
"""
import collections.abc
import enum
import warnings
from collections.abc import Iterable, Iterator, Mapping, MutableMapping
from typing import Any, TypeAlias, cast

from kopf._cogs.helpers import thirdparty
from kopf._cogs.structs import bodies, dicts
from kopf._core.actions import execution
from kopf._core.intents import causes

K8sObject: TypeAlias = MutableMapping[Any, Any] | thirdparty.PykubeObject | thirdparty.KubernetesModelSync | thirdparty.KubernetesModelAsync
K8sObjects: TypeAlias = K8sObject | Iterable[K8sObject]


class _UNSET(enum.Enum):
    token = enum.auto()


def append_owner_reference(
        objs: K8sObjects,
        owner: bodies.Body | None = None,
        *,
        controller: bool | None = True,
        block_owner_deletion: bool | None = True,
) -> None:
    """
    Append an owner reference to the resource(s), if it is not yet there.

    Note: the owned objects are usually not the one being processed,
    so the whole body can be modified, no patches are needed.
    """
    pass


def remove_owner_reference(
        objs: K8sObjects,
        owner: bodies.Body | None = None,
) -> None:
    """
    Remove an owner reference from the resource(s), if it is there.

    Note: the owned objects are usually not the one being processed,
    so the whole body can be modified, no patches are needed.
    """
    pass


def label(
        objs: K8sObjects,
        labels: Mapping[str, str | None] | _UNSET = _UNSET.token,
        *,
        forced: bool = False,
        nested: str | Iterable[dicts.FieldSpec] | None = None,
        force: bool | None = None,  # deprecated
) -> None:
    """
    Apply the labels to the object(s).
    """
    pass


def harmonize_naming(
        objs: K8sObjects,
        name: str | None | _UNSET = _UNSET.token,
        *,
        forced: bool = False,
        strict: bool = False,
) -> None:
    """
    Adjust the names or prefixes of the objects.

    In strict mode, the provided name is used as is. It can be helpful
    if the object is referred by that name in other objects.

    In non-strict mode (the default), the object uses the provided name
    as a prefix, while the suffix is added by Kubernetes remotely.
    The actual name should be taken from Kubernetes response
    (this is the recommended scenario).

    If the objects already have their own names, auto-naming is not applied,
    and the existing names are used as is.
    """
    pass


def adjust_namespace(
        objs: K8sObjects,
        namespace: str | None | _UNSET = _UNSET.token,
        *,
        forced: bool = False,
) -> None:
    """
    Adjust the namespace of the objects.

    If the objects already have the namespace set, it will be preserved.

    It is a common practice to keep the children objects in the same
    namespace as their owner, unless explicitly overridden at time of creation.
    """
    pass


def adopt(
        objs: K8sObjects,
        owner: bodies.Body | None = None,
        *,
        forced: bool = False,
        strict: bool = False,
        nested: str | Iterable[dicts.FieldSpec] | None = None,
) -> None:
    """
    The children should be in the same namespace, named after their parent, and owned by it.
    """
    pass


