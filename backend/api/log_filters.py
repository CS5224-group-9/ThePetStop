"""Logging filters. Presigned or signed file URLs must never reach the logs."""

import logging
import re

# The trailing slash is optional: a client may drop it
_TOKEN = re.compile(r"/local-files/[^/\s\"?]+")


class RedactLocalFileTokens(logging.Filter):
    """Replace the signed token in local file URLs with `<redacted>`.

    The token is the capability for a private pet file, so request lines such as
    `"PUT /api/v1/local-files/<token>/ HTTP/1.1" 200 0` must not show it.
    """

    def filter(self, record):
        message = record.getMessage()
        if "/local-files/" in message:
            record.msg = _TOKEN.sub("/local-files/<redacted>", message)
            record.args = ()
        return True
