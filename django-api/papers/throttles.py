from django.core.cache import cache
from rest_framework.throttling import BaseThrottle
from rest_framework.exceptions import Throttled
import time


class AnalyzeRateThrottle(BaseThrottle):
    """
    Limits analyze requests to 10 per minute per user.
    Uses Redis as the counter store.
    """
    RATE_LIMIT = 10       # max requests
    WINDOW = 60           # per 60 seconds

    def get_cache_key(self, request, view):
        # Unique key per user
        return f"throttle:analyze:{request.user.id}"

    def allow_request(self, request, view):
        cache_key = self.get_cache_key(request, view)

        # Get current request history from Redis
        # Returns list of timestamps of previous requests
        request_history = cache.get(cache_key, [])
        now = time.time()

        # Remove timestamps older than our window (60 seconds)
        request_history = [
            timestamp for timestamp in request_history
            if now - timestamp < self.WINDOW
        ]

        if len(request_history) >= self.RATE_LIMIT:
            # Too many requests — calculate wait time
            self.wait_time = self.WINDOW - (now - request_history[0])
            return False

        # Add current request timestamp and save back to Redis
        request_history.append(now)
        cache.set(cache_key, request_history, timeout=self.WINDOW)
        return True

    def wait(self):
        return self.wait_time