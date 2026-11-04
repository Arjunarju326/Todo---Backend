from rest_framework.authentication import SessionAuthentication


class CsrfExemptSessionAuthentication(SessionAuthentication):
    """Session auth that skips CSRF — safe here because Next.js same-origin rewrite is the only client."""

    def enforce_csrf(self, request):
        return
