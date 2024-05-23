import logging
import sys
import traceback
from typing import Any, Callable

from django.http import HttpRequest, HttpResponse

from studio.utils import get_logger

logger = get_logger(__name__)


class ExceptionLoggingMiddleware:
    """
    This middleware provides logging of exception in requests.
    """

    def __init__(self, get_response: Callable[[HttpRequest], Any]):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        return response

    def process_exception(self, request: HttpRequest, exception: Exception) -> None:
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
