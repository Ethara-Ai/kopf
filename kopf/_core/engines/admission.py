import abc
import asyncio
import base64
import copy
import json
import logging
import re
import urllib.parse
from collections.abc import Collection, Iterable
from typing import Any, AsyncContextManager, Literal, TypedDict

from kopf._cogs.aiokits import aiovalues
from kopf._cogs.clients import creating, errors, patching
from kopf._cogs.configs import configuration
from kopf._cogs.structs import bodies, diffs, ephemera, ids, patches, references, reviews
from kopf._core.actions import execution, lifecycles, loggers, progression
from kopf._core.intents import causes, filters, handlers, registries

logger = logging.getLogger(__name__)


class AdmissionError(execution.PermanentError):
    """
    Raised by admission handlers when an API operation under check is bad.

    An admission error behaves the same as :class:`kopf.PermanentError`,
    but provides admission-specific payload for the response:
    a message and a numeric code.

    This error type is preferred when selecting only one error to report back
    to apiservers as the admission review result --- in case multiple handlers
    are called in one admission request, i.e. when the webhook endpoints
    are not mapped to the handler ids (e.g. when configured manually).
    """
    def __init__(
            self,
            message: str | None = '',
            code: int | None = 500,
    ) -> None:
        super().__init__(message)
        self.code = code


class WebhookError(Exception):
    """
    Raised when a webhook request is bad, not an API operation under check.
    """


class MissingDataError(WebhookError):
    """
    An admission is requested but some expected data are missing.
    """


class UnknownResourceError(WebhookError):
    """
    An admission is requested for a resource that the operator does not handle.
    """


class AmbiguousResourceError(WebhookError):
    """
    An admission is requested for one resource, but multiple matches were found.
    """


class MemoGetter(metaclass=abc.ABCMeta):
    """
    An interface as a way to break the reverse dependency of modules:

    * The lower-level admission engine needs :class:`Memories` for memos.
    * The memories are implemented in the higher-level ``reactor.inventory``.
    * The inventory must be there in the high-level reactor because
      it requires specialised memory classes from ``daemons``, ``indexing``, …
    * And the inventory cannot be shifted down from the reactor to engines
      because it is not an engine semantically.

    Implemented by :class:`inventory.Memories` or by any of its views.
    """
    @abc.abstractmethod
    async def recall_memo(
            self,
            raw_body: bodies.RawBody,
            *,
            memobase: ephemera.AnyMemo | None = None,
            ephemeral: bool = False,
    ) -> ephemera.AnyMemo:
        raise NotImplementedError


async def serve_admission_request(
        # Required for all webhook servers, meaningless without it:
        request: reviews.Request,
        *,
        # Optional for webhook servers that can recognise this information:
        headers: reviews.Headers | None = None,
        sslpeer: reviews.SSLPeer | None = None,
        webhook: ids.HandlerId | None = None,
        reason: causes.WebhookType | None = None,  # TODO: undocumented: requires typing clarity!
        # Injected by partial() from spawn_tasks():
        settings: configuration.OperatorSettings,
        memories: MemoGetter,
        memobase: ephemera.AnyMemo,
        registry: registries.OperatorRegistry,
        insights: references.Insights,
        indices: ephemera.Indices,
) -> reviews.Response:
    """
    The actual and the only implementation of the :class:`WebhookFn` protocol.

    This function is passed to all webhook servers/tunnels to be called
    whenever a new admission request is received.

    Some parameters are provided by the framework itself via partial binding,
    so that the resulting function matches the ``WebhookFn`` protocol. Other
    parameters are passed by the webhook servers when they call the function.
    """
    pass


def find_resource(
        *,
        request: reviews.Request,
        insights: references.Insights,
) -> references.Resource:
    """
    Identify the requested resource by its meta-information (as discovered).
    """
    pass


def build_response(
        *,
        request: reviews.Request,
        outcomes: dict[ids.HandlerId, execution.Outcome],
        warnings: Collection[str],
        jsonpatch: patches.JSONPatch,
) -> reviews.Response:
    """
    Construct the admission review response to a review request.
    """
    pass


async def admission_webhook_server(
        *,
        settings: configuration.OperatorSettings,
        registry: registries.OperatorRegistry,
        insights: references.Insights,
        webhookfn: reviews.WebhookFn,
        container: aiovalues.Container[reviews.WebhookClientConfig],
) -> None:

    # Verify that the operator is configured properly (after the startup activities are done).
    has_admission = bool(registry._webhooks.get_all_handlers())
    if settings.admission.server is None and has_admission:
        raise Exception(
            "Admission handlers exist, but no admission server/tunnel is configured "
            "in `settings.admission.server`. "
            "More: https://docs.kopf.dev/en/stable/admission/")

    # Do not start the endpoints until resources are scanned.
    # Otherwise, we generate 404 "Not Found" for requests that arrive too early.
    await insights.ready_resources.wait()

    # Communicate all the client configs the server yields: both the initial one and the updates.
    # On each such change, the configuration manager will wake up and reconfigure the webhooks.
    if settings.admission.server is None:
        await asyncio.Event().wait()
    elif isinstance(settings.admission.server, AsyncContextManager):
        async with settings.admission.server as server:
            async for client_config in server(webhookfn):
                await container.set(client_config)
    else:
        async for client_config in settings.admission.server(webhookfn):
            await container.set(client_config)


async def validating_configuration_manager(
        *,
        registry: registries.OperatorRegistry,
        settings: configuration.OperatorSettings,
        insights: references.Insights,
        container: aiovalues.Container[reviews.WebhookClientConfig],
) -> None:
    await configuration_manager(
        reason=causes.WebhookType.VALIDATING,
        selector=references.VALIDATING_WEBHOOK,
        registry=registry, settings=settings,
        insights=insights, container=container,
    )


async def mutating_configuration_manager(
        *,
        registry: registries.OperatorRegistry,
        settings: configuration.OperatorSettings,
        insights: references.Insights,
        container: aiovalues.Container[reviews.WebhookClientConfig],
) -> None:
    await configuration_manager(
        reason=causes.WebhookType.MUTATING,
        selector=references.MUTATING_WEBHOOK,
        registry=registry, settings=settings,
        insights=insights, container=container,
    )


async def configuration_manager(
        *,
        reason: causes.WebhookType,
        selector: references.Selector,
        registry: registries.OperatorRegistry,
        settings: configuration.OperatorSettings,
        insights: references.Insights,
        container: aiovalues.Container[reviews.WebhookClientConfig],
) -> None:
    """
    Manage the webhook configurations dynamically.

    This is one of an operator's root tasks that run forever.
    If exited, the whole operator exits as by an error.

    The manager waits for changes in one of these:

    * Observed resources in the cluster (via insights).
    * A new webhook client config yielded by the webhook server.

    On either of these occasion, the manager rebuilds the webhook configuration
    and applies it to the specified configuration resources in the cluster
    (for which it needs some RBAC permissions).
    Besides, it also creates a webhook configuration resource if it is absent.
    """

    # Do nothing if not managed. The root task cannot be skipped from creation,
    # since the managed mode is only set at the startup activities.
    if settings.admission.managed is None:
        await asyncio.Event().wait()
        return

    # Wait until the prerequisites for managing are available (scanned from the cluster).
    await insights.ready_resources.wait()
    resource = await insights.backbone.wait_for(selector)
    all_handlers = registry._webhooks.get_all_handlers()
    all_handlers = [h for h in all_handlers if h.reason == reason]

    # Optionally (if configured), pre-create the configuration objects if they are absent.
    # Use the try-or-fail strategy instead of check-and-do -- to reduce the RBAC requirements.
    try:
        await creating.create_obj(
            settings=settings,
            resource=resource,
            logger=logger,
            name=settings.admission.managed,
        )
    except errors.APIConflictError:
        pass  # exists already
    except errors.APIForbiddenError:
        logger.error(f"Not enough RBAC permissions to create a {resource}.")
        raise

    # Execute either when actually changed (yielded from the webhook server),
    # or the condition is chain-notified (from the insights: on resources/namespaces revision).
    # Ignore inconsistencies: they are expected -- the server fills the defaults.
    client_config: reviews.WebhookClientConfig | None = None
    try:
        async for client_config in container.as_changed():
            logger.info(f"Reconfiguring the {reason.value} webhook {settings.admission.managed}.")
            webhooks = build_webhooks(
                all_handlers,
                resources=insights.webhook_resources,
                name_suffix=settings.admission.managed,
                client_config=client_config)
            await patching.patch_obj(
                settings=settings,
                resource=resource,
                namespace=None,
                name=settings.admission.managed,
                patch=patches.Patch({'webhooks': webhooks}),
                logger=logger,
            )
    finally:
        # Attempt to remove all managed webhooks, except for the strict ones.
        if client_config is not None:
            logger.info(f"Cleaning up the admission webhook {settings.admission.managed}.")
            webhooks = build_webhooks(
                all_handlers,
                resources=insights.webhook_resources,
                name_suffix=settings.admission.managed,
                client_config=client_config,
                persistent_only=True)
            await patching.patch_obj(
                settings=settings,
                resource=resource,
                namespace=None,
                name=settings.admission.managed,
                patch=patches.Patch({'webhooks': webhooks}),
                logger=logger,
            )


def build_webhooks(
        handlers_: Iterable[handlers.WebhookHandler],
        *,
        resources: Iterable[references.Resource],
        name_suffix: str,
        client_config: reviews.WebhookClientConfig,
        persistent_only: bool = False,
) -> list[dict[str, Any]]:
    """
    Construct the content for ``[Validating|Mutating]WebhookConfiguration``.

    This function concentrates all conventions how Kopf manages the webhook.
    """
    return [
        {
            'name': _normalize_name(handler.id, suffix=name_suffix),
            'sideEffects': 'NoneOnDryRun' if handler.side_effects else 'None',
            'failurePolicy': 'Ignore' if handler.ignore_failures else 'Fail',
            'matchPolicy': 'Equivalent',
            'rules': [
                {
                    'apiGroups': [resource.group],
                    'apiVersions': [resource.version],
                    'resources': (
                        [resource.plural] if handler.subresource is None else
                        [f'{resource.plural}/{handler.subresource}']
                    ),
                    'operations': list(handler.operations or ['*']),
                    'scope': '*',  # doesn't matter since a specific resource is used.
                }
                for resource in resources
                if handler.selector is not None  # None is used only in sub-handlers, ignore here.
                if handler.selector.check(resource)
            ],
            'objectSelector': _build_labels_selector(handler.labels),
            'clientConfig': _inject_handler_id(client_config, handler.id),
            'timeoutSeconds': 30,  # a permitted maximum is 30.
            'admissionReviewVersions': ['v1', 'v1beta1'],  # only those understood by Kopf itself.
        }
        for handler in handlers_
        if not persistent_only or handler.persistent
    ]


class MatchExpression(TypedDict, total=False):
    key: str
    operator: Literal['Exists', 'DoesNotExist', 'In', 'NotIn']
    values: Collection[str] | None


def _build_labels_selector(labels: filters.MetaFilter | None) -> dict[str, Any] | None:
    # https://kubernetes.io/docs/concepts/overview/working-with-objects/labels/#resources-that-support-set-based-requirements
    exprs: Collection[MatchExpression] = [
        {'key': key, 'operator': 'Exists'} if val is filters.MetaFilterToken.PRESENT else
        {'key': key, 'operator': 'DoesNotExist'} if val is filters.MetaFilterToken.ABSENT else
        {'key': key, 'operator': 'In', 'values': [str(val)]}
        for key, val in (labels or {}).items()
        if not callable(val)
    ]
    return {'matchExpressions': exprs} if exprs else None


BAD_WEBHOOK_NAME = re.compile(r'[^\w\d\.-]')


def _normalize_name(id: ids.HandlerId, suffix: str) -> str:
    """
    Normalize the webhook name to what Kubernetes accepts as normal.

    The restriction is: *a lowercase RFC 1123 subdomain must consist
    of lower case alphanumeric characters, \'-\' or \'.\',
    and must start and end with an alphanumeric character.*

    The actual name is not that important, it is for informational purposes
    only. In the managed configurations, it will be rewritten every time.
    """
    name = f'{id}'.replace('/', '.').replace('_', '-')  # common cases, for beauty
    name = BAD_WEBHOOK_NAME.sub(lambda s: s.group(0).encode('utf-8').hex(), name)  # uncommon cases
    return f'{name}.{suffix}' if suffix else name


def _inject_handler_id(config: reviews.WebhookClientConfig, id: ids.HandlerId) -> reviews.WebhookClientConfig:
    config = copy.deepcopy(config)

    url_id = urllib.parse.quote(id)
    url = config.get('url')
    if url is not None:
        config['url'] = f'{url.rstrip("/")}/{url_id}'

    service = config.get('service')
    if service is not None:
        path = service.get('path', '')
        service['path'] = f"{path}/{url_id}"

    return config
