# Contributing to RescueNet X 2.0

Thank you for helping improve RescueNet X 2.0. This guide describes how changes are made and merged.

## Branches

| Branch | Purpose |
|---|---|
| `main` | Stable, protected baseline. Always in a working state. |
| `extra-features` | Development branch for new features and improvements. |

Both branches are protected by repository rulesets: they cannot be deleted or force-pushed, and `main` accepts changes **only through pull requests**.

## Workflow

1. **Sync first.** Bring `extra-features` up to date with `main` before starting new work, and again regularly while you work:
   ```bash
   git checkout extra-features
   git fetch origin
   git merge --ff-only origin/main     # fast-forward only; never rewrites history
   ```
   If a fast-forward is not possible, merge `origin/main` into `extra-features` with a normal merge commit and resolve conflicts.
2. **Develop** on `extra-features` (or a short-lived branch created from it for larger features).
3. **Test** (see below) and make sure the frontend builds.
4. **Push normally** to `extra-features`:
   ```bash
   git push origin extra-features
   ```
5. **Open a pull request** from `extra-features` into `main`. Describe what changed and how it was tested. Merge it on GitHub (merge or squash) once the checks above pass and conversations are resolved.
6. **Sync again.** After the pull request is merged, fast-forward `extra-features` to the new `main` so both branches match.

## Testing before merging

Run the relevant checks and fix any failure before opening or merging a pull request.

```bash
# Backend (from the repository root or backend/)
python -m pytest -q

# Frontend (from rescuenet-x2/frontend/)
npm ci
npm run build
```

- Add or update tests for any change in behaviour.
- Tests that need Ollama or the downloaded photo models are skipped automatically when those are absent.
- Photo-model and flood-model changes should include updated numbers in `docs/model_evaluation.md` or `docs/vision_evaluation.md`.

## Rules

- **Do not force-push**, rewrite published history (rebase, amend, or filter published commits), or bypass branch protection or rulesets.
- **Do not commit secrets or private data.** This includes `.env` files, passwords, tokens, `backend/.jwt_secret`, `backend/.admin_password`, local databases (`*.db`) that may hold real accounts or incidents, uploaded incident photos, and any private incident or personal records. These paths are already in `.gitignore`; check `git status` before committing. If a secret is committed by mistake, rotate it immediately and tell the maintainer.
- **Keep the demo accounts for development only.** Turn `SEED_DEMO_USERS` off for any real deployment (see the README).
- **Label data honestly** as OBSERVED, PREDICTED or SIMULATED, and do not present sample data as real.
- **Do not change the dispatch approval rule** (commander approval for 5 or more people, or HIGH/CRITICAL severity) without discussion.

## Git identity and attribution

- Use your own Git identity for commits and keep the repository's existing configuration as it is. The project owner's identity is `bhavaniv2750-dev <247392732+bhavaniv2750-dev@users.noreply.github.com>`.
- Do not add automatic AI attribution (for example `Co-Authored-By:` lines for AI tools, or session links) to commit messages or pull request descriptions. If you use an AI coding tool, disable its commit attribution setting.
- Credit human collaborators with their own `Co-authored-by:` trailer if they contributed to a commit.

## Commit messages

Use a short imperative summary line (about 72 characters), then a blank line and a few lines explaining what changed and why.

## Questions

Open an issue on GitHub, or ask the project maintainer.
