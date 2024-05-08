import logging
import sys
import traceback
from typing import Any

from studio.utils import get_logger

logger = get_logger(__name__)


class ExceptionLoggingMiddleware:
    """
    This middleware provides logging of exception in requests.
    """

    def __init__(self, get_response: Any):
        self.get_response = get_response

    def __call__(self, request: object) -> Any:
        response = self.get_response(request)
        return response

    def process_exception(self, request: Any, exception: Any) -> None:
        """
        Processes exceptions during handling of a http request.
        Logs them with ERROR level.
        """
        _, _, stacktrace = sys.exc_info()
        msg = f"Processing exception {exception} at {request.path} | "
        msg += f"GET {request.GET} | "
        msg += "".join(traceback.format_tb(stacktrace)).replace("\n", "\\n")
        logger.error(msg)
        return None
