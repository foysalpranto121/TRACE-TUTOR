"""Cookie middleware for TRACE Tutor.

Every browser gets a signed, HttpOnly `trace_device` cookie the first time it talks to the API.
It carries no personal data - just a random id - and is attached to interaction logs so the
research team can distinguish devices (shared lab computers, returning participants) without
identifying anyone. JavaScript cannot read it (HttpOnly) and it cannot be forged (signed with
SECRET_KEY).
"""
import secrets

from django.conf import settings
from django.core import signing

DEVICE_SALT = 'trace.device'


class TraceCookiesMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        device_id, is_new = self._device_id(request)
        request.device_id = device_id
        response = self.get_response(request)
        if is_new:
            response.set_cookie(
                settings.DEVICE_COOKIE_NAME,
                signing.dumps(device_id, salt=DEVICE_SALT),
                max_age=settings.DEVICE_COOKIE_AGE,
                httponly=True,
                samesite='Lax',
                secure=settings.SESSION_COOKIE_SECURE,
            )
        return response

    @staticmethod
    def _device_id(request):
        raw = request.COOKIES.get(settings.DEVICE_COOKIE_NAME)
        if raw:
            try:
                return signing.loads(raw, salt=DEVICE_SALT), False
            except signing.BadSignature:
                pass  # tampered or from an old SECRET_KEY: issue a fresh id
        return secrets.token_urlsafe(12), True
