"""GraphQL error handling.

Every error in a GraphQL result passes through `ErrorLoggingExtension` before the
response goes to the client. What happens to it depends on where it came from:

- **Public errors** (`PublicError` subclasses, see errors.py — "Invalid email or
  password", "Recipe not found", ...): the message was written for the client, so the
  error passes through unchanged. Logged at WARNING; not sent to Sentry — these are
  normal outcomes, not bugs.
- **GraphQL-level errors** (syntax errors, unknown fields, missing variables, ...):
  produced by graphql-core from the client's own query, so there is no underlying
  exception and the message is safe. Passed through, logged at WARNING.
- **Anything else** is unexpected: a bug, a database hiccup, whatever. Its full details
  (type, traceback) are logged via structlog and reported to Sentry, but the client only
  ever sees a generic "Internal server error" — never the raw exception message, which
  could leak internal details (file paths, SQL, stack traces).
"""

import sentry_sdk
import structlog
from graphql import GraphQLError
from strawberry.extensions import SchemaExtension

from errors import PublicError

logger = structlog.get_logger("recipegraph.graphql")


def _sanitize(error: GraphQLError) -> GraphQLError:
    original = error.original_error

    if original is None:
        logger.warning("graphql_request_error", path=error.path, message=error.message)
        return error

    if isinstance(original, PublicError):
        logger.warning(
            "graphql_public_error",
            path=error.path,
            exception_type=type(original).__name__,
            message=error.message,
        )
        return error

    logger.error(
        "graphql_resolver_error",
        path=error.path,
        exception_type=type(original).__name__,
        exc_info=original,
    )
    sentry_sdk.capture_exception(original)

    return GraphQLError(
        message="Internal server error",
        nodes=error.nodes,
        source=error.source,
        positions=error.positions,
        path=error.path,
    )


class ErrorLoggingExtension(SchemaExtension):
    def on_operation(self):
        yield

        result = self.execution_context.result
        if result is None or not result.errors:
            return

        result.errors = [_sanitize(error) for error in result.errors]
