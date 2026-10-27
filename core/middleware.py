import logging
import time

logger = logging.getLogger('goalbet')


class RequestTimingMiddleware:
    """Log request method/path/status/duration without headers or body data."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        started = time.monotonic()
        response = self.get_response(request)
        duration_ms = round((time.monotonic() - started) * 1000, 1)
        logger.info('request method=%s path=%s status=%s duration_ms=%s', request.method, request.path, response.status_code, duration_ms)
        return response
