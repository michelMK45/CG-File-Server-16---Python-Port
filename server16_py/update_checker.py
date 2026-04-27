from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass


@dataclass
class UpdateCheckResult:
    ok: bool
    update_available: bool
    current_version: str
    latest_version: str = ""
    release_url: str = ""
    error: str = ""


class GithubReleaseChecker:
    def __init__(self, owner: str, repo: str, timeout_seconds: float = 6.0) -> None:
        self.owner = owner
        self.repo = repo
        self.timeout_seconds = timeout_seconds

    def check_latest_release(self, current_version: str) -> UpdateCheckResult:
        url = f"https://api.github.com/repos/{self.owner}/{self.repo}/releases/latest"
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "CGFS16-Python-Port-UpdateChecker",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as exc:
            return UpdateCheckResult(
                ok=False,
                update_available=False,
                current_version=current_version,
                error=f"HTTP {exc.code}: {exc.reason}",
            )
        except urllib.error.URLError as exc:
            return UpdateCheckResult(
                ok=False,
                update_available=False,
                current_version=current_version,
                error=f"Network error: {exc.reason}",
            )
        except Exception as exc:
            return UpdateCheckResult(
                ok=False,
                update_available=False,
                current_version=current_version,
                error=f"Unexpected error: {exc}",
            )

        latest_tag = str(payload.get("tag_name") or "").strip()
        latest_version = self._normalize_version(latest_tag)
        current_normalized = self._normalize_version(current_version)

        if not latest_version:
            return UpdateCheckResult(
                ok=False,
                update_available=False,
                current_version=current_version,
                error="Latest release tag is missing or invalid",
            )

        return UpdateCheckResult(
            ok=True,
            update_available=self._is_remote_newer(latest_version, current_normalized),
            current_version=current_version,
            latest_version=latest_version,
            release_url=str(payload.get("html_url") or ""),
        )

    @staticmethod
    def _normalize_version(version: str) -> str:
        trimmed = version.strip()
        if not trimmed:
            return ""
        if trimmed.lower().startswith("v"):
            trimmed = trimmed[1:]
        return trimmed

    @classmethod
    def _is_remote_newer(cls, remote_version: str, local_version: str) -> bool:
        return cls._version_tuple(remote_version) > cls._version_tuple(local_version)

    @staticmethod
    def _version_tuple(version: str) -> tuple[int, ...]:
        parts: list[int] = []
        for token in version.split("."):
            match = re.match(r"(\d+)", token)
            if not match:
                parts.append(0)
                continue
            parts.append(int(match.group(1)))
        return tuple(parts)
