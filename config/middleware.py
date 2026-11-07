"""Extra security headers that Django does not set by itself."""

# Content Security Policy: the browser may only load scripts, styles, images and
# forms from our own site and the Bootstrap CDN. Injected <script> tags or inline
# event handlers (onclick=...) are blocked, which stops most XSS attacks.
CONTENT_SECURITY_POLICY = "; ".join([
    "default-src 'self'",
    "script-src 'self' https://cdn.jsdelivr.net",
    "style-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'",  # style="..." attributes
    "img-src 'self' data:",                                       # Bootstrap's built-in icons
    "font-src 'self' https://cdn.jsdelivr.net",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",                                     # nobody may put us in an <iframe>
])

# Features this app never needs: deny them to every page and embedded content.
PERMISSIONS_POLICY = "camera=(), microphone=(), geolocation=(), payment=(), usb=()"


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.headers.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)
        response.headers.setdefault("Permissions-Policy", PERMISSIONS_POLICY)
        return response