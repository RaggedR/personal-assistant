"""Error types that map onto process exit codes.

Exit codes are part of the CLI contract: a caller (human or agent) must be able
to distinguish "you are not set up" from "the thing you asked for is not there"
from "Google said no", without parsing prose.
"""


class PaError(Exception):
    """Base class. ``exit_code`` is what ``main`` returns to the shell."""

    exit_code = 1


class AuthError(PaError):
    """No usable credentials, or the ones we have lack a required scope."""

    exit_code = 3


class NotFoundError(PaError):
    """A message, thread, event or contact does not exist."""

    exit_code = 4


class UsageError(PaError):
    """The arguments do not make sense together."""

    exit_code = 2


class ApiError(PaError):
    """Google returned an error we cannot interpret further."""

    exit_code = 5


class ConfirmationRequired(PaError):
    """A destructive or outbound action was attempted without confirmation.

    This exists to make Robin's hard rule ("never send an email without
    explicit permission") a property of the tool rather than only of the
    instructions given to an agent.
    """

    exit_code = 7
