"""Command-line entry point for the job application agent.

Typical flow:

    python -m jobagent.cli search              # pull + score new listings
    python -m jobagent.cli list --top 10        # see best matches
    python -m jobagent.cli generate --id 12     # write a tailored cover letter
    python -m jobagent.cli apply --id 12        # open the listing, mark applied
    python -m jobagent.cli update --id 12 --status offer
    python -m jobagent.cli status               # pipeline dashboard
"""
from __future__ import annotations

import argparse
import sys
import textwrap
import webbrowser
from pathlib import Path
from typing import Any

import yaml

from jobagent import db, materials
from jobagent.scoring import score_job
from jobagent.sources import fetch_all

ROOT = Path(__file__).resolve().parent.parent
PROFILE_PATH = ROOT / "config" / "profile.yaml"
PROFILE_EXAMPLE_PATH = ROOT / "config" / "profile.yaml.example"
RESUME_PATH = ROOT / "config" / "resume.md"
OUTPUT_DIR = ROOT / "output"


def load_profile() -> dict[str, Any]:
    if not PROFILE_PATH.exists():
        sys.exit(
            f"Missing {PROFILE_PATH}.\n"
            f"Copy the template first:\n"
            f"  cp {PROFILE_EXAMPLE_PATH} {PROFILE_PATH}\n"
            f"then edit it with your real details."
        )
    with open(PROFILE_PATH, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_resume_text() -> str:
    if RESUME_PATH.exists():
        return RESUME_PATH.read_text(encoding="utf-8")
    return ""


def cmd_search(args: argparse.Namespace) -> None:
    profile = load_profile()
    db.init_db()

    sources = args.sources.split(",") if args.sources else None
    jobs, errors = fetch_all(search=args.query, sources=sources)
    for err in errors:
        print(f"[warn] {err}", file=sys.stderr)

    new_count = 0
    with db.connect() as conn:
        for nj in jobs:
            result = score_job(nj.title, nj.description, nj.tags, profile)
            job = db.Job(
                source=nj.source,
                external_id=nj.external_id,
                title=nj.title,
                company=nj.company,
                url=nj.url,
                location=nj.location,
                remote=nj.remote,
                description=nj.description,
                tags=nj.tags,
                category=result.category,
                ai_score=result.ai_score,
                exclusion_hits=",".join(result.exclusion_hits),
                fit_score=result.fit_score,
                status="excluded" if result.excluded else "scored",
            )
            _, was_new = db.upsert_job(conn, job)
            if was_new:
                new_count += 1

    source_desc = ", ".join(sources) if sources else "all sources"
    print(f"Fetched {len(jobs)} listings from {source_desc}.")
    print(f"Added {new_count} new jobs to the pipeline.")


def _print_table(rows: list, columns: list[tuple[str, str, int]]) -> None:
    header = "  ".join(name.ljust(width) for name, _, width in columns)
    print(header)
    print("-" * len(header))
    for row in rows:
        cells = []
        for name, key, width in columns:
            val = str(row[key]) if row[key] is not None else ""
            if len(val) > width:
                val = val[: width - 1] + "…"
            cells.append(val.ljust(width))
        print("  ".join(cells))


def cmd_list(args: argparse.Namespace) -> None:
    db.init_db()
    with db.connect() as conn:
        rows = db.list_jobs(
            conn,
            status=args.status,
            min_fit_score=args.min_score,
            limit=args.top,
        )
    if not rows:
        print("No jobs match. Run `search` first, or loosen your filters.")
        return
    _print_table(
        rows,
        [
            ("ID", "id", 4),
            ("Fit", "fit_score", 5),
            ("Status", "status", 15),
            ("Category", "category", 32),
            ("Title", "title", 40),
            ("Company", "company", 24),
        ],
    )


def cmd_generate(args: argparse.Namespace) -> None:
    profile = load_profile()
    resume_text = load_resume_text()
    db.init_db()
    with db.connect() as conn:
        row = db.get_job(conn, args.id)
        if row is None:
            sys.exit(f"No job with id {args.id}")
        job = dict(row)
        letter = materials.generate_cover_letter(job, profile, resume_text)

        OUTPUT_DIR.mkdir(exist_ok=True)
        safe_company = "".join(c if c.isalnum() else "_" for c in job["company"])[:40]
        out_path = OUTPUT_DIR / f"{job['id']}_{safe_company}_cover_letter.md"
        out_path.write_text(letter, encoding="utf-8")

        db.update_job(conn, job["id"], materials_path=str(out_path))
        if job["status"] not in ("applied", "interviewing", "offer", "rejected", "withdrawn"):
            db.set_status(conn, job["id"], "materials_ready")

    print(f"Cover letter written to {out_path}")
    print(f"Apply at: {job['url']}")


def cmd_apply(args: argparse.Namespace) -> None:
    """Marks a job as applied. Never auto-submits a form — it opens the
    listing (or just prints the URL with --no-browser) so you make the
    final submit click yourself, keeping you compliant with job boards'
    anti-bot Terms of Service."""
    db.init_db()
    with db.connect() as conn:
        row = db.get_job(conn, args.id)
        if row is None:
            sys.exit(f"No job with id {args.id}")
        job = dict(row)

        if not args.no_browser:
            webbrowser.open(job["url"])
        else:
            print(job["url"])

        if job.get("materials_path"):
            print(f"Materials: {job['materials_path']}")
        else:
            print("Tip: run `generate --id "
                  f"{job['id']}` first for a tailored cover letter.")

        if args.mark_applied:
            db.set_status(conn, job["id"], "applied")
            print(f"Job {job['id']} marked as applied.")
        else:
            print(
                f"Opened listing. Once you submit it, run:\n"
                f"  python -m jobagent.cli apply --id {job['id']} --mark-applied --no-browser"
            )


def cmd_update(args: argparse.Namespace) -> None:
    db.init_db()
    with db.connect() as conn:
        row = db.get_job(conn, args.id)
        if row is None:
            sys.exit(f"No job with id {args.id}")
        extra = {}
        if args.notes is not None:
            extra["notes"] = args.notes
        db.set_status(conn, args.id, args.status, **extra)
    print(f"Job {args.id} -> {args.status}")


def cmd_status(args: argparse.Namespace) -> None:
    profile = load_profile()
    db.init_db()
    with db.connect() as conn:
        counts = db.status_counts(conn)
        offers = db.list_jobs(conn, status="offer", order_by="id")

    goal = profile.get("hiring_goal", 6)
    landed = len(offers)

    print("Pipeline:")
    for status in db.VALID_STATUSES:
        n = counts.get(status, 0)
        if n:
            print(f"  {status:<15} {n}")
    print()
    print(f"Goal: {landed}/{goal} remote AI-heavy roles landed.")
    if offers:
        print("Landed:")
        for row in offers:
            print(f"  - {row['title']} @ {row['company']} ({row['url']})")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jobagent",
        description=textwrap.dedent(__doc__ or ""),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_search = sub.add_parser("search", help="Fetch and score new remote listings.")
    p_search.add_argument("--query", default=None, help="Free-text search term, e.g. 'prompt engineer'.")
    p_search.add_argument("--sources", default=None, help="Comma-separated source names (default: all).")
    p_search.set_defaults(func=cmd_search)

    p_list = sub.add_parser("list", help="List jobs in the pipeline.")
    p_list.add_argument("--status", default=None, help="Filter by status (e.g. scored, applied).")
    p_list.add_argument("--min-score", type=float, default=None, dest="min_score")
    p_list.add_argument("--top", type=int, default=25)
    p_list.set_defaults(func=cmd_list)

    p_gen = sub.add_parser("generate", help="Generate a tailored cover letter for a job.")
    p_gen.add_argument("--id", type=int, required=True)
    p_gen.set_defaults(func=cmd_generate)

    p_apply = sub.add_parser(
        "apply",
        help="Open a job listing for final manual submission and track it.",
    )
    p_apply.add_argument("--id", type=int, required=True)
    p_apply.add_argument("--no-browser", action="store_true", help="Don't open a browser tab.")
    p_apply.add_argument(
        "--mark-applied",
        action="store_true",
        help="Mark this job 'applied' now (use after you've actually submitted it).",
    )
    p_apply.set_defaults(func=cmd_apply)

    p_update = sub.add_parser("update", help="Manually update a job's status (e.g. after a reply).")
    p_update.add_argument("--id", type=int, required=True)
    p_update.add_argument("--status", required=True, choices=sorted(db.VALID_STATUSES))
    p_update.add_argument("--notes", default=None)
    p_update.set_defaults(func=cmd_update)

    p_status = sub.add_parser("status", help="Show pipeline counts and progress toward your goal.")
    p_status.set_defaults(func=cmd_status)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
