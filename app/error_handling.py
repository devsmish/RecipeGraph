"""GraphQL error handling.

Every exception a resolver raises ends up here before the response goes to the client.
Two very different things happen to it, depending on what kind of exception it is:

- "Safe" business exceptions (InvalidCredentialsError, NotAuthenticatedError, etc.) were
  written with a message that's already fine to show a client — these pass through
  unchanged.
- Anything else is unexpected: a bug, a database hiccup, whatever. Its full details
  (type, traceback) are logged via structlog and reported to Sentry, but the client only
  ever sees a generic "Internal server error" — never the raw exception message, which
  could leak internal details (file paths, SQL, stack traces).
"""

import sentry_sdk
import structlog
from graphql import GraphQLError
from strawberry.extensions import SchemaExtension

logger = structlog.get_logger("recipegraph.graphql")

_SAFE_EXCEPTIONS = frozenset(
    {
        "InvalidCredentialsError",
        "UsernameOrEmailTakenError",
        "InvalidRefreshTokenError",
        "NotAuthenticatedError",
    }
)


class ErrorLoggingExtension(SchemaExtension):
    def on_operation(self):
        yield

        result = self.execution_context.result
        if result is None or not result.errors:
            return

        safe_errors = []
        for error in result.errors:
            original = error.original_error
            exception_type = type(original).__name__ if original is not None else None

            logger.error(
                "graphql_resolver_error",
                path=error.path,
                exception_type=exception_type,
                exc_info=original,
            )

            if exception_type in _SAFE_EXCEPTIONS:
                safe_errors.append(error)
                continue

            # Unexpected — report to Sentry and hide the real message from the client.
            if original is not None:
                sentry_sdk.capture_exception(original)

            safe_errors.append(
                GraphQLError(
                    message="Internal server error",
                    nodes=error.nodes,
                    source=error.source,
                    positions=error.positions,
                    path=error.path,
                )
            )

        result.errors = safe_errors
