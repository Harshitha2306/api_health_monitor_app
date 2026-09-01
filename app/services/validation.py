import ipaddress
import json
from urllib.parse import urlparse


ALLOWED_METHODS = {"GET", "HEAD", "POST"}


def validate_endpoint_url(endpoint_url):
    if not isinstance(endpoint_url, str) or not endpoint_url.strip():
        return "Endpoint URL is required."
    try:
        parsed = urlparse(endpoint_url.strip())
        if parsed.scheme.lower() not in {"http", "https"}:
            return "Only HTTP and HTTPS endpoint URLs are supported."
        if not parsed.hostname or parsed.username or parsed.password:
            return "Enter a valid endpoint URL without embedded credentials."
        try:
            address = ipaddress.ip_address(parsed.hostname)
            if address.is_loopback or address.is_link_local or address.is_unspecified:
                return "Loopback and link-local endpoint addresses are not allowed."
        except ValueError:
            if parsed.hostname.lower() in {"localhost", "localhost.localdomain"}:
                return "Localhost endpoints are not allowed."
    except (TypeError, ValueError):
        return "Enter a valid HTTP or HTTPS endpoint URL."
    return None


def validate_service_payload(payload, partial=False):
    errors = {}
    if not partial or "name" in payload:
        if not str(payload.get("name", "")).strip():
            errors["name"] = "Service name is required."
    if not partial or "endpoint_url" in payload:
        message = validate_endpoint_url(payload.get("endpoint_url"))
        if message:
            errors["endpoint_url"] = message
    method = str(payload.get("method", "GET")).upper()
    if method not in ALLOWED_METHODS:
        errors["method"] = "Method must be GET, HEAD, or POST."
    ranges = {
        "expected_status": (100, 599), "interval_seconds": (10, 86400),
        "timeout_seconds": (1, 120), "response_threshold_ms": (1, 300000),
        "failure_threshold": (1, 100),
    }
    for field, (minimum, maximum) in ranges.items():
        if partial and field not in payload:
            continue
        value = payload.get(field)
        if value in (None, ""):
            continue
        try:
            if not minimum <= int(value) <= maximum:
                raise ValueError
        except (TypeError, ValueError):
            errors[field] = f"Must be a number between {minimum} and {maximum}."
    if method == "POST" and payload.get("post_body"):
        try:
            body = payload["post_body"]
            json.loads(body if isinstance(body, str) else json.dumps(body))
        except (TypeError, ValueError):
            errors["post_body"] = "POST body must be valid JSON."
    return errors
