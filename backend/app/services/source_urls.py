"""Pure URL checks. This module opens no network connections."""

import ipaddress
import re
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit, urlunsplit


def normalize_host(value: str) -> str:
    host = value.lower()
    if not host.isascii() or host != host.strip() or len(host) > 253 or host.endswith("."):
        raise ValueError("A canonical ASCII hostname is required")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError("IP literal hosts are forbidden")
    labels = host.split(".")
    if len(labels) < 2 or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in labels):
        raise ValueError("Invalid public hostname")
    if not re.fullmatch(r"[a-z]{2,63}|xn--[a-z0-9-]{2,59}", labels[-1]):
        raise ValueError("Invalid public top-level domain")
    if labels[-1] in {"localhost", "local", "internal", "test", "invalid", "example", "home", "lan"}:
        raise ValueError("Local and reserved domains are forbidden")
    return host


def canonical_recipe_url(value: str) -> str:
    if len(value) > 2000 or any(ord(char) <= 32 or ord(char) == 127 for char in value) or "\\" in value:
        raise ValueError("Invalid recipe URL")
    if re.search(r"%(?![0-9a-fA-F]{2})", value):
        raise ValueError("Malformed URL escaping")
    try:
        parsed = urlsplit(value)
        if parsed.scheme != "https" or parsed.username is not None or parsed.password is not None or parsed.port not in (None, 443):
            raise ValueError("Only HTTPS URLs without credentials or custom ports are allowed")
        host = normalize_host(parsed.hostname or "")
        if parsed.netloc.casefold() not in {host, f"{host}:443"}:
            raise ValueError("Malformed or noncanonical URL authority")
        path = unquote(parsed.path or "/", errors="strict")
        if re.search(r"%[0-9a-fA-F]{2}", path):
            raise ValueError("Nested URL escaping is forbidden")
    except (UnicodeError, ValueError) as exc:
        raise ValueError("Invalid HTTPS recipe URL") from exc
    if any(ord(char) < 32 or ord(char) == 127 or char == "\\" for char in path):
        raise ValueError("Unsafe URL path")
    parts = [part.casefold() for part in path.split("/") if part]
    if not parts or any(part in {"category", "categories", "tag", "tags", "search", "page", ".", ".."} for part in parts):
        raise ValueError("A recipe-specific URL is required")
    query = [(key, item) for key, item in parse_qsl(parsed.query, keep_blank_values=True, max_num_fields=50)
        if not key.casefold().startswith("utm_") and key.casefold() not in {"fbclid", "gclid", "msclkid"}]
    if any(key.casefold() in {"token", "access_token", "api_key", "signature", "password", "authorization"}
            or re.search(r"%[0-9a-fA-F]{2}", key + item)
            or any(ord(char) < 32 or ord(char) == 127 for char in key + item) for key, item in query):
        raise ValueError("Private or unsafe URL query parameters are forbidden")
    result = urlunsplit(("https", host, quote(path, safe="/-._~!$&'()*+,;=:@"), urlencode(sorted(query)), ""))
    if len(result) > 2000:
        raise ValueError("Canonical URL exceeds the supported length")
    return result


def validate_redirect_hops(initial_source_hosts: set[str], redirect_hosts: set[str], urls: list[str], addresses: dict[str, list[str]]):
    """Validate an offline transport plan; a future transport must pin the returned IPs."""
    if not urls or len(urls) > 6:
        raise ValueError("Redirect chain exceeds the allowed hop count")
    validated = []
    for index, url in enumerate(urls):
        canonical = canonical_recipe_url(url)
        host = urlsplit(canonical).hostname
        allowed = initial_source_hosts if index == 0 else initial_source_hosts | redirect_hosts
        if host not in allowed:
            raise ValueError("Redirect leaves the reviewed hosts")
        resolved = addresses.get(host, [])
        if not resolved:
            raise ValueError("No validated public DNS addresses")
        canonical_addresses = []
        for value in resolved:
            address = ipaddress.ip_address(value)
            if (not address.is_global or address.is_multicast or address.is_reserved
                    or (isinstance(address, ipaddress.IPv6Address) and (
                        address.ipv4_mapped or address.sixtofour or address.teredo
                        or address in ipaddress.ip_network("64:ff9b::/96")
                        or address in ipaddress.ip_network("64:ff9b:1::/48")))):
                raise ValueError("Private or special-use DNS address is forbidden")
            canonical_addresses.append(str(address))
        validated.append((canonical, tuple(sorted(set(canonical_addresses)))))
    return validated
