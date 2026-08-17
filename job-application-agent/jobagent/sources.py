"""Fetchers for public, developer-facing remote-job APIs.

Both APIs used here are free, public, unauthenticated endpoints that the
job boards themselves publish for programmatic consumption (Remotive's API
is explicitly documented for third-party use; RemoteOK publishes a JSON
mirror of its listings at /api). No scraping, no login, no ToS-violating
automation happens in this module — it only reads public job listings.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from html import unescape
from typing import Any, Callable, Iterable, Optional

import requests

REMOTIVE_URL = "https://remotive.com/api/remote-jobs"
REMOTEOK_URL = "https://remoteok.com/api"
USER_AGENT = "job-application-agent/0.1 (personal job-search tool)"
REQUEST_TIMEOUT = 20


@dataclass
class NormalizedJob:
    source: str
    external_id: str
    title: str
    company: str
    url: str
    location: str
    remote: bool
    description: str
    tags: str


def _strip_html(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def fetch_remotive(
    search: Optional[str] = None,
    session: Optional[requests.Session] = None,
) -> list[NormalizedJob]:
    """Fetch listings from Remotive's public remote-jobs API."""
    sess = session or requests
    params = {"search": search} if search else {}
    resp = sess.get(
        REMOTIVE_URL,
        params=params,
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    payload = resp.json()
    jobs = []
    for item in payload.get("jobs", []):
        jobs.append(
            NormalizedJob(
                source="remotive",
                external_id=str(item.get("id")),
                title=item.get("title", "").strip(),
                company=item.get("company_name", "").strip(),
                url=item.get("url", ""),
                location=item.get("candidate_required_location", ""),
                remote=True,
                description=_strip_html(item.get("description", "")),
                tags=",".join(item.get("tags", []) or []),
            )
        )
    return jobs


def fetch_remoteok(session: Optional[requests.Session] = None) -> list[NormalizedJob]:
    """Fetch listings from RemoteOK's public JSON API.

    The first element of the response is a legal/metadata notice, not a
    job, and is skipped.
    """
    sess = session or requests
    resp = sess.get(
        REMOTEOK_URL,
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    payload = resp.json()
    jobs = []
    for item in payload:
        if not isinstance(item, dict) or "id" not in item or "position" not in item:
            continue  # skip the legal-notice header row
        tags = item.get("tags", []) or []
        jobs.append(
            NormalizedJob(
                source="remoteok",
                external_id=str(item.get("id")),
                title=(item.get("position") or "").strip(),
                company=(item.get("company") or "").strip(),
                url=item.get("url", "") or f"https://remoteok.com/remote-jobs/{item.get('id')}",
                location=item.get("location", "") or "Remote",
                remote=True,
                description=_strip_html(item.get("description", "")),
                tags=",".join(tags),
            )
        )
    return jobs


SOURCES: dict[str, Callable[..., list[NormalizedJob]]] = {
    "remotive": fetch_remotive,
    "remoteok": fetch_remoteok,
}


def fetch_all(
    search: Optional[str] = None,
    sources: Optional[Iterable[str]] = None,
    session: Optional[requests.Session] = None,
) -> tuple[list[NormalizedJob], list[str]]:
    """Fetch from every requested source, collecting per-source errors instead
    of failing the whole run when one API is unreachable."""
    selected = list(sources) if sources else list(SOURCES)
    jobs: list[NormalizedJob] = []
    errors: list[str] = []
    for name in selected:
        fetch_fn = SOURCES.get(name)
        if fetch_fn is None:
            errors.append(f"Unknown source: {name}")
            continue
        try:
            kwargs: dict[str, Any] = {"session": session}
            if name == "remotive":
                kwargs["search"] = search
            jobs.extend(fetch_fn(**kwargs))
        except Exception as exc:  # noqa: BLE001 - surface any failure per-source
            errors.append(f"{name}: {exc}")
    return jobs, errors
