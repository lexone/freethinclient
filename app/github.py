"""Bounded GitHub HTTPS requests. Never forward a token to a redirect host."""
import json
import re
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.github.com"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def github_get(path, token, *, binary=False, limit=2_000_000):
    if not path.startswith("/repos/") or ".." in path:
        raise ValueError("Endpoint GitHub inválido")
    headers = {"User-Agent": "freethinclient", "Accept": "application/octet-stream" if binary else "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = "Bearer " + token.strip()
    opener = urllib.request.build_opener(NoRedirect)
    req = urllib.request.Request(API + path, headers=headers)
    try:
        response = opener.open(req, timeout=30)
    except urllib.error.HTTPError as exc:
        if exc.code not in (301, 302, 303, 307, 308) or not binary:
            raise RuntimeError(f"GitHub HTTP {exc.code}: confira repositório, token e permissões.") from None
        location = exc.headers.get("Location", "")
        parsed = urllib.parse.urlsplit(location)
        allowed = ("release-assets.githubusercontent.com", "objects.githubusercontent.com")
        if parsed.scheme != "https" or parsed.hostname not in allowed or parsed.username or parsed.port not in (None, 443):
            raise ValueError("Redirecionamento de download não autorizado")
        # A new request with NO Authorization. No second redirect is allowed.
        response = opener.open(urllib.request.Request(location, headers={"User-Agent": "freethinclient"}), timeout=60)
    with response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Download excede limite permitido")
    return data if binary else json.loads(data)


def valid_repository(value):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value):
        raise ValueError("Repositório deve ser DONO/NOME")
    return value
