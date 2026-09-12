# Agent instructions

Maintain this as a small, reliable public open-source project. Read
[CONTRIBUTING.md](CONTRIBUTING.md) for setup and validation and
[SECURITY.md](SECURITY.md) for trust boundaries and private reporting.

## Protect private data

- Treat tracked files, commit metadata, issues, pull requests, CI output, and
  release archives as public. Review each surface before publishing to it.
- Use synthetic examples and fixtures. Never copy real conversations, desktop
  captures, audio, transcripts, runtime traces, credentials, private session
  links, personal email addresses, or machine-specific paths into public files.
- Keep necessary local investigation artifacts under ignored `docs/private/`
  or `benchmarks/`, with restrictive permissions. Do not add internal handoffs,
  audit evidence, experiment journals, or generated logs to the repository.
  Ignored files are still private: do not upload or package them.
- Use your own GitHub noreply identity for both author and committer metadata.
  Preserve contributor credit; do not impersonate another contributor.
- Report findings by file and rule, without echoing secret values. Scanners
  supplement manual review and cannot guarantee that data is safe to publish.
- If a real credential is exposed, stop publishing the affected material,
  report it privately, and arrange revocation or rotation. Removing a file does
  not remove its history. Explain any retained fork, clone, or GitHub cache
  exposure; do not claim those copies have been erased.

## Keep the project lean and dependable

- Prefer focused changes and existing abstractions. Add dependencies only for
  a concrete need; consider maintenance, compatibility, and licensing costs.
- Keep the README focused on installation and use. Put durable reference
  material in the relevant existing guide; avoid duplicate development docs.
- Remove obsolete tooling, dead code, and orphaned tests together. Keep tests
  that protect user behavior, failure handling, privacy, and security boundaries.
  Test count alone is not a reason to remove coverage.
- Use temporary directories, fake providers, and mocked desktop/audio services
  in automated tests. Keep tests offline and independent of personal accounts,
  API keys, microphones, screens, and a running desktop. Paid or live integration
  checks must remain explicit opt-ins.
- Preserve policy checks, confirmation boundaries, path restrictions, and
  sandboxing. Fix the test environment instead of weakening production controls.
- Update user documentation when behavior changes. Keep supported Python
  versions, package metadata, installers, and CI consistent. Preserve licenses
  and attribution; document material limitations without overstating guarantees.

## Publish only reviewed work

- Inspect the current branch, working tree, and remote heads first. Preserve
  unrelated and concurrent edits. Use a separate clean worktree when a checkout
  contains unfinished work; never reset, clean, or stash it indiscriminately.
- Vision is currently excluded from publication. Keep its code, integration,
  docs, tests, and mixed-file changes local until the maintainer explicitly
  authorizes publishing it. A request to clean or push voice does not include it.
- Enable repository hooks with `git config core.hooksPath .githooks`. Stage
  explicit paths, review `git diff --cached`, and run:

  ```sh
  git diff --cached --check
  python3 tools/check_public_files.py --staged
  ```

- Before pushing, scan the complete ancestry of every proposed branch or tag
  with `python3 tools/check_public_files.py --history <revision>`. Check commit
  messages and identities as well as file contents. Do not bypass failed hooks
  or privacy CI, and do not reintroduce old unsanitized ancestry through a merge.
- Run the relevant checks in CONTRIBUTING.md. Code changes require the behavior
  suite; docs-only edits need link, whitespace, and publication checks. For
  packaging changes, inspect both source and wheel archives for private files.
- Push only explicitly intended refs to the verified remote. Do not use blanket
  `--all` or `--mirror` pushes. History rewrites and branch deletion need explicit
  authorization; use exact leases for authorized force pushes.
- Follow the maintainer's existing authorization without asking again for the
  same action. After publishing, verify remote heads and required CI, and report
  the actual result and any remaining limitations.

## Code Review Rules

- Flag private data in content or metadata, real-data fixtures, and changes that
  allow private artifacts into source archives, wheels, logs, or CI output.
- Flag bypassed publication checks, weakened execution boundaries, and removed
  regression coverage without an equivalent check or removed feature.
- Flag publication of excluded vision work or unrelated local changes.
