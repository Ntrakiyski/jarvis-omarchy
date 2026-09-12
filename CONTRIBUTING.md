# Contributing

Small, focused improvements are welcome. Describe the user-visible problem and
check for an existing issue before starting a large feature. The project targets
Omarchy on Linux; the supported Python baseline is 3.11.

Automated contributors must also follow [AGENTS.md](AGENTS.md), which covers
public-data hygiene, maintenance standards, and safe publishing.

## Set up

```sh
git clone https://github.com/wombatoperator/omarchy-voice.git
cd omarchy-voice
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
git config core.hooksPath .githooks
```

Use the GitHub noreply email shown in your account's email settings for this
repository's `git config user.email`. Commit and push hooks check staged content,
commit identities, and complete pushed ancestry. Do not bypass a privacy failure.

The editable Python install provides `omarchy-voice`; it does not install desktop
bindings, widgets, or a user service. Use `./install.sh` when you want that
integration. Unit tests do not require an API key or a running Omarchy desktop.

## Validate a change

```sh
python -m unittest discover -s tests
python -m compileall -q src tests tools
bash -n install.sh uninstall.sh share/install-paths.sh
python tools/check_public_files.py --staged
python -m build
```

CI runs the full unit suite on Python 3.11 and 3.14, builds the distribution, and
checks publication history. Local test sockets must be permitted; a sandbox that
blocks them can prevent network and control-socket tests from running. Do not
weaken production security to make a test pass.

Keep tests that verify behavior, failure handling, and execution boundaries.
When removing a feature or development-only tool, remove its orphaned tests too.
Avoid tests that only repeat implementation details. Use synthetic data, fake
providers, and temporary directories; never commit a real desktop transcript or
credential as a fixture.

Optional integration checks run outside CI:

| Command | Scope |
| --- | --- |
| `python tools/check_live.py --connect` | Paid API protocol probe with synthetic silence; no microphone or desktop access |
| `python tools/check_tasks.py` | Temporary systemd workers and bubblewrap with a fake provider; no model API calls |
| `python tools/trace_summary.py /path/to/live-trace.jsonl` | Local trace analysis; output may still contain private identifiers/errors |

Read a check's help and requirements before running it. Keep generated evidence
under ignored `benchmarks/` or `docs/private/` and inspect it before sharing.

## Find the code

| Location | Responsibility |
| --- | --- |
| `src/omarchy_voice/` | Voice engines, desktop tools, policy, and durable workers |
| `tests/` | Automated behavior and security regressions |
| `tools/` | Publication checks, opt-in integration checks, trace analysis |
| `share/`, `omarchy/`, `plugin/` | Desktop configuration, command wrappers, and widgets |
| `docs/` | User and contributor reference guides |

The package version lives in `src/omarchy_voice/__init__.py`. `pyproject.toml`
reads it when building. Wheels contain the Python application; source archives
also contain the installer, integration files, guides, and tests.

## Send a pull request

Explain the problem, the resulting behavior, and how you verified it. Include
reproduction steps or a synthetic example when useful. Update the relevant guide
when a command, configuration option, or trust boundary changes. Keep unrelated
formatting and refactoring separate. Be respectful and discuss the code and its
behavior rather than the contributor.

Report vulnerabilities through [SECURITY.md](SECURITY.md), not a public issue or
pull request containing private data. See the [MIT License](LICENSE) for project
licensing.
