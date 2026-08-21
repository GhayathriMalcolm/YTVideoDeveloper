"""Lightweight update check against GitHub Releases. No-op until UPDATE_REPO is set."""

import requests

from .version import UPDATE_REPO, __version__


def _parse_version(v: str):
    return tuple(int(p) for p in v.lstrip("v").split("."))


def check_for_update(timeout: float = 3.0):
    """Returns (download_url, latest_version) if a newer release exists, else None.
    Fails silently (returns None) on any network/parse error - an update check
    must never block or crash the app from starting."""
    if not UPDATE_REPO:
        return None
    try:
        resp = requests.get(
            f"https://api.github.com/repos/{UPDATE_REPO}/releases/latest",
            timeout=timeout,
            headers={"Accept": "application/vnd.github+json"},
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        latest_tag = data.get("tag_name", "")
        if not latest_tag:
            return None
        if _parse_version(latest_tag) <= _parse_version(__version__):
            return None
        assets = data.get("assets", [])
        installer = next((a for a in assets if a["name"].lower().endswith(".exe")), None)
        download_url = installer["browser_download_url"] if installer else data.get("html_url")
        return download_url, latest_tag.lstrip("v")
    except Exception:
        return None
