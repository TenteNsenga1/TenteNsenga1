"""Generates tailored application materials for a scored job.

Works fully offline via a plain template. If ANTHROPIC_API_KEY is set in
the environment, tries to produce a better-tailored cover letter through
the Claude API first, falling back to the template on any error (missing
key, network failure, bad response) so the pipeline never blocks on it.
"""
from __future__ import annotations

import os
from typing import Any, Optional

import requests

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
REQUEST_TIMEOUT = 30


def _template_cover_letter(job: dict[str, Any], profile: dict[str, Any]) -> str:
    candidate = profile.get("candidate", {})
    name = candidate.get("name", "Your Name")
    email = candidate.get("email", "")
    summary = candidate.get("summary", "").strip()
    skills = candidate.get("top_skills", [])
    skills_line = ", ".join(skills) if skills else ""

    lines = [
        f"Dear {job.get('company', 'Hiring Team')} team,",
        "",
        f"I'm applying for the {job.get('title', 'open')} role. {summary}".strip(),
        "",
    ]
    if skills_line:
        lines.append(f"Relevant skills: {skills_line}.")
        lines.append("")
    lines += [
        "I'm looking for remote, async-friendly work where I can lean heavily "
        "on AI tools day to day, ramp up quickly, and do consistently good "
        "work with minimal live back-and-forth. I'd welcome the chance to "
        "bring that focus to this role.",
        "",
        "Thank you for your time and consideration.",
        "",
        name,
        email,
    ]
    return "\n".join(lines) + "\n"


def _ai_cover_letter(job: dict[str, Any], profile: dict[str, Any], resume_text: str) -> Optional[str]:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    candidate = profile.get("candidate", {})
    prompt = f"""Write a concise, specific, non-generic cover letter (under 250 words,
plain text, no markdown) for this candidate applying to this job.
Tone: direct, professional, understated — no hype/buzzwords, no claims the
resume doesn't support. Do not invent experience that isn't in the resume.

CANDIDATE SUMMARY:
{candidate.get('summary', '')}

CANDIDATE TOP SKILLS:
{', '.join(candidate.get('top_skills', []))}

CANDIDATE RESUME:
{resume_text}

JOB TITLE: {job.get('title', '')}
COMPANY: {job.get('company', '')}
JOB DESCRIPTION:
{(job.get('description') or '')[:4000]}

Sign off with the candidate's name: {candidate.get('name', '')}
"""
    try:
        resp = requests.post(
            ANTHROPIC_API_URL,
            headers={
                "x-api-key": api_key,
                "anthropic-version": ANTHROPIC_VERSION,
                "content-type": "application/json",
            },
            json={
                "model": DEFAULT_MODEL,
                "max_tokens": 600,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        parts = data.get("content", [])
        text = "".join(p.get("text", "") for p in parts if p.get("type") == "text")
        return text.strip() or None
    except Exception:
        return None


def generate_cover_letter(
    job: dict[str, Any],
    profile: dict[str, Any],
    resume_text: str = "",
) -> str:
    ai_letter = _ai_cover_letter(job, profile, resume_text)
    if ai_letter:
        return ai_letter
    return _template_cover_letter(job, profile)
