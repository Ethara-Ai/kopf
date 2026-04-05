import abc
import copy
import json
from collections.abc import Collection, Iterable
from typing import Any, cast

from kopf._cogs.configs import conventions
from kopf._cogs.structs import bodies, dicts, patches


class DiffBaseStorage(conventions.StorageKeyMarkingConvention,
                      conventions.StorageStanzaCleaner,
                      metaclass=abc.ABCMeta):
    """
    Store the base essence for diff calculations, i.e. last handled state.

    The "essence" is a snapshot of meaningful fields, which must be tracked
    to identify the actual changes on the object (or absence of such).

    Used in the handling routines to check if there were significant changes
    (i.e. not the internal and system changes, like the uids, links, etc.),
    and to get the exact per-field diffs for the specific handler functions.

    Conceptually similar to how ``kubectl apply`` stores the applied state
    on any object, and then uses that for the patch calculation:
    https://kubernetes.io/docs/concepts/overview/object-management-kubectl/declarative-config/
    """

    def __init__(self, ignored_fields: Iterable[dicts.FieldSpec] | None = None) -> None:
        super().__init__()
        self.ignored_fields = list(ignored_fields or [])  # materialize the iterable

    def build(
            self,
            *,
            body: bodies.Body,
            extra_fields: Iterable[dicts.FieldSpec] | None = None,
    ) -> bodies.BodyEssence:
        """
        Extract only the relevant fields for the state comparisons.

        The framework ignores all the system fields (mostly from metadata)
        and the status stanza completely. Except for some well-known and useful
        metadata, such as labels and annotations (except for sure garbage).

        A special set of fields can be provided even if they are supposed
        to be removed. This is used, for example, for handlers which react
        to changes in the specific fields in the status stanza,
        while the rest of the status stanza is removed.

        It is generally not a good idea to override this method in custom
        stores, unless a different definition of an object's essence is needed.
        """
        pass

    @abc.abstractmethod
    def fetch(
            self,
            *,
            body: bodies.Body,
    ) -> bodies.BodyEssence | None:
        raise NotImplementedError

    @abc.abstractmethod
    def store(
            self,
            *,
            body: bodies.Body,
            patch: patches.Patch,
            essence: bodies.BodyEssence,
    ) -> None:
        raise NotImplementedError


class AnnotationsDiffBaseStorage(conventions.StorageKeyFormingConvention, DiffBaseStorage):

    def __init__(
            self,
            *,
            prefix: str = 'kopf.zalando.org',
            key: str = 'last-handled-configuration',
            ignored_fields: Iterable[dicts.FieldSpec] | None = None,
            v1: bool = True,  # will be switched to False a few releases later
    ) -> None:
        super().__init__(prefix=prefix, v1=v1, ignored_fields=ignored_fields)
        self.key = key





class StatusDiffBaseStorage(DiffBaseStorage):

    def __init__(
            self,
            *,
            name: str = 'kopf',
            field: dicts.FieldSpec = 'status.{name}.last-handled-configuration',
            ignored_fields: Iterable[dicts.FieldSpec] | None = None,
    ) -> None:
        super().__init__(ignored_fields=ignored_fields)
        self._name = name
        real_field = field.format(name=self._name) if isinstance(field, str) else field
        self._field = dicts.parse_field(real_field)

    @property
    def field(self) -> dicts.FieldPath:
        return self._field

    @field.setter
    def field(self, field: dicts.FieldSpec) -> None:
        real_field = field.format(name=self._name) if isinstance(field, str) else field
        self._field = dicts.parse_field(real_field)





class MultiDiffBaseStorage(DiffBaseStorage):

    def __init__(
            self,
            storages: Collection[DiffBaseStorage],
    ) -> None:
        super().__init__()
        self.storages = storages



