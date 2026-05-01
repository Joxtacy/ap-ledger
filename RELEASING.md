# Releasing

Releases are cut from the GitHub Actions UI. The flow:

1. Go to **Actions → release → Run workflow** in this repo.
2. Enter a version (e.g. `0.2.0`, no leading `v`). Tick **dry_run** if you want
   to see the proposed `CHANGELOG.md` and `pyproject.toml` diff without
   committing or pushing.
3. The workflow regenerates `CHANGELOG.md` from `cliff.toml`, bumps
   `pyproject.toml`, refreshes `uv.lock` via `uv lock --no-upgrade`, commits
   as `github-actions[bot]`, tags `vX.Y.Z`, pushes, then dispatches `build.yml`
   against the new tag.
4. `build.yml` builds Linux/macOS/Windows binaries, packages them, and
   publishes a GitHub Release with the per-version changelog section + a
   downloads table as the body.
5. Locally, run `jj git fetch` to pull the bump commit and the new tag back
   into your working copy.

## Preview the changelog locally

Before triggering, you can see what the next release notes will look like:

```sh
git cliff --unreleased         # what's accumulated since the last tag
git cliff --tag v0.2.0         # full file as it would be written for v0.2.0
```

Install `git-cliff` via `brew install git-cliff` (macOS) or `cargo install
git-cliff --locked`.

## Hiding commit types from the changelog

Edit `cliff.toml`'s `commit_parsers`. Set `skip = true` for commit prefixes
that should not appear in user-facing notes (`ci:`, `style:`, `chore:`, etc.
are already skipped). Re-run `git cliff` to verify.

## Empty-release guard

The workflow refuses to release if no commits since the last tag produce
changelog entries. If you hit this, either there's nothing new worth
releasing, or all your commits use skipped types — adjust `cliff.toml` or
land a real change first.

## Bootstrap (only relevant for `v0.1.0`)

The very first release does not go through `release.yml`. The `v0.1.0` tag is
created manually so that the bump-commit and changelog already exist when
subsequent dispatches run. Sequence:

```sh
# CHANGELOG.md and cliff.toml are already in place.
git tag -a v0.1.0 -m "Release v0.1.0"
git push origin main
git push origin v0.1.0
```

Pushing a tag from your laptop (not via `GITHUB_TOKEN`) does trigger
`build.yml`'s release job, so the v0.1.0 GitHub Release is created with
artifacts and the bootstrap changelog as its body.

## Why `git`, not `jj`, for tag pushes

`jj git push` does not push tags by default, and this project's release
workflow runs in CI where only `git` is available. After CI pushes a tag,
sync your local working copy with `jj git fetch`.
