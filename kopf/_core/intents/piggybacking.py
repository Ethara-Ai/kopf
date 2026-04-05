"""
Rudimentary piggybacking on the known K8s API clients for authentication.

Kopf is not a client library, and avoids bringing too much logic
for proper authentication, especially all the complex auth-providers.

Instead, it uses the existing clients, triggers the (re-)authentication
in them, and extracts the basic credentials for its own use.

.. seealso::
    :mod:`credentials` and :func:`authentication`.
"""
import inspect
import os
from collections.abc import Sequence
from typing import Any

import yaml

from kopf._cogs.configs import configuration
from kopf._cogs.helpers import typedefs
from kopf._cogs.structs import credentials

# Keep as constants to make them patchable. Higher priority is more preferred.
PRIORITY_OF_CLIENT: int = 10
PRIORITY_OF_ASYNC_CLIENT: int = 15
PRIORITY_OF_PYKUBE: int = 20

# Rudimentary logins are added only if the clients are absent, so the priorities can overlap.
PRIORITY_OF_KUBECONFIG: int = 10
PRIORITY_OF_SERVICE_ACCOUNT: int = 20










# We keep the official client library auto-login only because it was
# an implied behavior before switching to pykube -- to keep it so (implied).


# This is basically a copy of `login_via_client` changed to use the
# kubernetes_asyncio client library.






def login_with_service_account(
        *,
        settings: configuration.OperatorSettings,
        **_: Any,
) -> credentials.ConnectionInfo | None:
    """
    A minimalistic login handler that can get raw data from a service account.

    Authentication capabilities can be limited to keep the code short & simple.
    No parsing or sophisticated multi-step token retrieval is performed.

    This login function is intended to make Kopf runnable in trivial cases
    when neither pykube-ng nor the official client library are installed.
    """
    pass




def login_with_kubeconfig(
        *,
        settings: configuration.OperatorSettings,
        **_: Any,
) -> credentials.ConnectionInfo | None:
    """
    A minimalistic login handler that can get raw data from a kubeconfig file.

    Authentication capabilities can be limited to keep the code short & simple.
    No parsing or sophisticated multi-step token retrieval is performed.

    This login function is intended to make Kopf runnable in trivial cases
    when neither pykube-ng nor the official client library are installed.
    """
    pass
