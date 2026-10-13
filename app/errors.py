"""Errors that are safe to show to API clients.

A GraphQL resolver can fail in two very different ways:

- an *expected* business failure ("Invalid email or password", "Recipe not found") —
  the message was written for the client and is fine to return as-is;
- an *unexpected* failure (a bug, a database hiccup) — its message may contain SQL, file
  paths or other internals, so the client only ever gets "Internal server error"
  (see error_handling.py).

Every expected error derives from `PublicError`, and that is the only thing the error
handler checks. To add a new client-visible error, subclass `PublicError` — there is no
list to remember to update. Anything that does *not* derive from it is treated as
unexpected, i.e. hidden from the client and reported to Sentry.
"""


class PublicError(Exception):
    """Base class for errors whose message is intended for the API client."""
