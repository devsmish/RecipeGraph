"""Parsing of client-supplied IDs.

IDs reach the API as plain strings (`strawberry.ID`). A malformed one is a mistake made by
the client, not a bug in the server, so it must produce a clear message — not the generic
"Internal server error" (and a Sentry report) that an uncaught `ValueError` would cause.
"""

import uuid

from errors import PublicError


class InvalidIdError(PublicError):
    def __init__(self, field_name: str) -> None:
        # The offending value is deliberately not echoed back: it may be arbitrarily long
        # or crafted, and naming the field is enough for the client to fix the request.
        super().__init__(f'Invalid ID for "{field_name}": expected a UUID')
        self.field_name = field_name


def parse_uuid(value: object, field_name: str) -> uuid.UUID:
    """Convert a client-supplied ID to a UUID, or raise `InvalidIdError` naming the field.

    `field_name` is the GraphQL name the client used (camelCase, e.g. "categoryId"), so the
    message points at the exact argument or input field that needs fixing.
    """
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        raise InvalidIdError(field_name) from None
