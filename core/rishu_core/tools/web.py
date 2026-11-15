"""Web search and page reading. Everything returned here is untrusted data."""

from __future__ import annotations

import ipaddress
import re
import socket
from collections.abc import Callable
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx

from .registry import ToolResult

SearchBackend = Callable[[str, int], list[dict[str, str]]]
Resolver = Callable[[str], list[str]]

_USER_AGENT = (
    "Mozilla/5.0 (compatible; RishuAssistant/0.1; +https://github.com/neeleshyadav603/RishuAI)"
)


def ddgs_backend(query: str, max_results: int) -> list[dict[str, str]]:
    """Free metasearch through the ``ddgs`` package (no API key)."""
    from ddgs import DDGS

    rows = DDGS().text(query, max_results=max_results) or []
    return [
        {"title": row.get("title", ""), "url": row.get("href", ""), "snippet": row.get("body", "")}
        for row in rows
    ]


def web_search(
    query: str, backend: SearchBackend | None = None, max_results: int = 5
) -> ToolResult:
    query = query.strip()
    if not query:
        return ToolResult(False, "The search query is empty.")
    try:
        rows = (backend or ddgs_backend)(query, max_results)
    except ImportError:
        return ToolResult(False, "Web search is not installed on this device (package 'ddgs').")
    except Exception as exc:  # noqa: BLE001 - search engines fail in many ways
        return ToolResult(
            False, f"Web search failed: {type(exc).__name__}. Check the internet connection."
        )
    rows = [row for row in rows if row.get("url")][:max_results]
    if not rows:
        return ToolResult(
            True, f"No results found for: {query}", untrusted=True, source="web_search", data=[]
        )
    lines = [
        f"[{i}] {row.get('title', '').strip()}\n    {row['url']}\n    {row.get('snippet', '').strip()}"
        for i, row in enumerate(rows, 1)
    ]
    return ToolResult(True, "\n".join(lines), untrusted=True, source="web_search", data=rows)


def _system_resolver(host: str) -> list[str]:
    return [info[4][0] for info in socket.getaddrinfo(host, None)]


def check_public_url(url: str, resolver: Resolver | None = None) -> str | None:
    """Return an error message if ``url`` must not be fetched, else ``None``.

    Blocks non-http(s) schemes and hosts on the local machine or private
    network, so a web page cannot make Rishu read local services.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return "only http and https pages can be read"
    host = parsed.hostname.lower()
    if host == "localhost" or host.endswith((".local", ".localhost", ".internal")):
        return "local addresses are not allowed"
    try:
        addresses = [host] if _is_ip(host) else (resolver or _system_resolver)(host)
    except OSError:
        return "the site address could not be resolved"
    for address in addresses:
        try:
            if not ipaddress.ip_address(address.split("%")[0]).is_global:
                return "local or private network addresses are not allowed"
        except ValueError:
            return "the site address could not be resolved"
    return None


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


class _TextExtractor(HTMLParser):
    _SKIP = {"script", "style", "noscript", "svg", "head", "nav", "footer", "form"}
    _BLOCK = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "tr", "section", "article"}

    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._skip_depth += 1
        elif tag in self._BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self._SKIP and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data):
        if not self._skip_depth:
            self.parts.append(data)


def extract_text(html: str) -> str:
    """Main text of a page: trafilatura when installed, a simple fallback otherwise."""
    try:
        import trafilatura

        text = trafilatura.extract(html, include_comments=False, include_tables=True)
        if text and len(text) > 200:
            return text.strip()
    except Exception:  # noqa: BLE001, S110 - optional dependency, fall back below
        pass
    parser = _TextExtractor()
    parser.feed(html)
    text = "".join(parser.parts)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def read_page(
    url: str,
    *,
    transport: httpx.BaseTransport | None = None,
    resolver: Resolver | None = None,
    max_chars: int = 6000,
    max_bytes: int = 2_000_000,
    timeout: float = 15.0,
) -> ToolResult:
    if "://" not in url:
        url = "https://" + url.strip()
    try:
        with httpx.Client(
            transport=transport, timeout=timeout, headers={"User-Agent": _USER_AGENT}
        ) as client:
            for _ in range(6):  # follow redirects by hand so every hop is checked
                problem = check_public_url(url, resolver)
                if problem:
                    return ToolResult(False, f"Cannot read this page: {problem}.")
                with client.stream("GET", url) as response:
                    if response.is_redirect and response.headers.get("location"):
                        url = urljoin(url, response.headers["location"])
                        continue
                    if response.status_code >= 400:
                        return ToolResult(
                            False, f"The page returned an error ({response.status_code})."
                        )
                    ctype = response.headers.get("content-type", "").lower()
                    if ctype and not any(
                        kind in ctype for kind in ("text/html", "text/plain", "xhtml")
                    ):
                        return ToolResult(
                            False, f"This link is not a readable web page ({ctype.split(';')[0]})."
                        )
                    chunks, size = [], 0
                    for chunk in response.iter_bytes():
                        chunks.append(chunk)
                        size += len(chunk)
                        if size >= max_bytes:
                            break
                    raw = b"".join(chunks)[:max_bytes]
                    encoding = response.encoding or "utf-8"
                break
            else:
                return ToolResult(False, "Cannot read this page: too many redirects.")
    except httpx.HTTPError as exc:
        return ToolResult(False, f"Could not load the page: {type(exc).__name__}.")
    html = raw.decode(encoding, errors="replace")
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    title = re.sub(r"\s+", " ", title_match.group(1)).strip() if title_match else ""
    text = extract_text(html) if "<" in html[:2000] else html.strip()
    if not text:
        return ToolResult(
            False, "The page has no readable text (it may need JavaScript or a login)."
        )
    truncated = len(text) > max_chars
    body = text[:max_chars] + ("\n[...page truncated...]" if truncated else "")
    content = f"Title: {title}\nURL: {url}\n\n{body}"
    return ToolResult(True, content, untrusted=True, source=url, data={"url": url, "title": title})
