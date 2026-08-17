# Job Application Agent

A personal tool that finds remote, AI-heavy, low-customer-contact jobs,
scores them against a profile you define, drafts a tailored cover letter
for each one, and tracks your pipeline toward a goal (default: 6 roles
landed).

## What it automates, and what it deliberately doesn't

It automates:
- **Discovery** — pulls listings from public remote-job APIs (Remotive,
  RemoteOK) on a schedule you control.
- **Filtering** — scores every listing against 6 configurable target
  categories (AI data/model training, AI-assisted QA, AI-assisted
  writing, AI-assisted research/analysis, prompt engineering/automation,
  AI-assisted back-office) and auto-excludes roles that look
  customer-facing (sales, cold calling, call centers, phone support).
- **Materials** — drafts a tailored cover letter per job, optionally
  using the Claude API for a sharper first draft.
- **Tracking** — a local pipeline (new → scored → materials ready →
  applied → interviewing → offer/rejected) with a status dashboard.

It does **not** auto-submit application forms. `apply` opens the listing
and hands you the drafted materials so the actual submit click is yours.
This is intentional, not a missing feature: LinkedIn, Indeed, and most
ATS platforms explicitly prohibit automated/bot-submitted applications in
their Terms of Service, and a banned account would set you back further
than any time saved. The tool optimizes the slow parts (finding good-fit
roles, writing a first-draft cover letter) and leaves the one part that
carries real ToS/account risk to you — it takes a few seconds per job.

## Setup

```bash
cd job-application-agent
pip install -r requirements.txt

cp config/profile.yaml.example config/profile.yaml
cp config/resume.md.example config/resume.md
# edit both with your real info — these two files are gitignored on purpose,
# since this repo is public
```

Optional, for AI-drafted (rather than templated) cover letters:

```bash
cp .env.example .env
# add ANTHROPIC_API_KEY=... to .env, then:
export $(grep -v '^#' .env | xargs)
```

Without a key, `generate` still works — it fills a plain template from
your profile instead.

## Usage

```bash
# 1. Pull and score new listings (run this daily/weekly, e.g. via cron)
python -m jobagent.cli search
python -m jobagent.cli search --query "prompt engineer"   # narrow the search

# 2. See your best matches
python -m jobagent.cli list --top 15
python -m jobagent.cli list --status scored --min-score 5

# 3. Draft a tailored cover letter for one
python -m jobagent.cli generate --id 12

# 4. Open it, apply manually, then confirm
python -m jobagent.cli apply --id 12                                   # opens the listing
python -m jobagent.cli apply --id 12 --mark-applied --no-browser       # after you submit it

# 5. Record what happens next (you'll hear back by email, not this tool)
python -m jobagent.cli update --id 12 --status interviewing
python -m jobagent.cli update --id 12 --status offer

# 6. Check progress toward your goal
python -m jobagent.cli status
```

Everything is stored in a local SQLite DB at `data/jobs.db` (gitignored).

## Customizing the 6 target categories

Edit `config/profile.yaml` → `target_categories`. Each category has a
`name`, a `weight` (how much a match there boosts a job's `fit_score`),
and a list of `keywords` matched case-insensitively against the job's
title/description/tags. Add, remove, reweight, or add new categories
freely — the scoring logic (`jobagent/scoring.py`) doesn't hardcode
anything about the categories.

`exclusion_keywords` and `exclusion_threshold` in the same file control
what gets auto-marked `excluded` (sales, cold calling, call centers,
etc. by default) — tune this list to match how strict you want the
"no live customer-facing work" filter to be.

## Extending it

Ideas that weren't needed for the MVP but would be natural next steps:
- More sources: We Work Remotely (RSS), Wellfound, direct Greenhouse/Lever
  board APIs for companies you specifically want to target.
- Auto-detecting replies by connecting a read-only Gmail/IMAP check for
  interview invites, instead of updating status by hand.
- A `cron`/systemd timer wrapper around `search` so new matches show up
  automatically.

## Tests

```bash
python -m unittest discover -s tests -v
```

Tests are fully offline (HTTP calls are mocked), so they run without
network access.
