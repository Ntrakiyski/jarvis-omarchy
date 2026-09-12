#!/usr/bin/env python3
"""Publication guard. Reports locations/rules, never matched content or secrets."""
import argparse
from pathlib import Path, PurePosixPath
import re
import subprocess

RULES = {
    'private key': r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
    'OpenAI token': r'\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{30,}',
    'GitHub token': r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})',
    'AWS access key': r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b',
    'credential URL': r'https?://[^\s/]+:[^\s/@]+@',
    'personal home path': r'/home/(?!you(?:/|\b)|user(?:/|\b)|test(?:/|\b)|example(?:/|\b))[-A-Za-z0-9_]+/',
    'private coding-session link': r'https://claude\.ai/code/session_[A-Za-z0-9_-]+',
    'production session identifier': r'\blive_u7_[A-Za-z0-9]+',
    'copied conversation log': r'(?m)^\s*(?:\d{2}:\d{2}:\d{2}\s+)?(?:heard|reply|action)\s+[\x22\x27]',
    'personal email address': r'\b[A-Za-z0-9._%+-]+@(?:gmail|hotmail|outlook|yahoo|icloud|protonmail)\.com\b',
}
PRIVATE_NAMES = {'HANDOFF.md', 'bridge-mockup.html', 'omarchy-voice.html'}
PRIVATE_SUFFIXES = {'.jsonl', '.sqlite', '.sqlite3', '.db', '.log', '.pem', '.key', '.p12', '.pfx'}


def git(*args):
    return subprocess.check_output(['git', *args])


def private_path(name):
    path = PurePosixPath(name)
    return (any(part in ('benchmarks', 'private', 'secrets', '.venv') for part in path.parts)
            or path.suffix in PRIVATE_SUFFIXES
            or path.name.startswith('.env')
            or path.name in PRIVATE_NAMES
            or (path.parts[0] == 'docs' and re.search(r'(?:^|-)review(?:-|\.)', path.name)))


def scan(name, data, findings):
    if private_path(name):
        findings.add((name, 0, 'private/runtime file'))
    content = data.decode(errors='replace')
    for rule, pattern in RULES.items():
        for match in re.finditer(pattern, content):
            findings.add((name, content.count('\n', 0, match.start()) + 1, rule))


def scan_history(revision, findings):
    commits = git('rev-list', revision).decode().splitlines()
    seen = set()
    for commit in commits:
        metadata = git('show', '-s', '--format=%an <%ae>%n%cn <%ce>%n%B', commit)
        # Scan messages too; file-only scanning misses secrets in commit messages.
        scan('commit/' + commit[:12], metadata, findings)
        emails = git('show', '-s', '--format=%ae%n%ce', commit).decode().splitlines()
        if any(email != 'noreply@github.com' and not email.endswith('@users.noreply.github.com')
               for email in emails):
            findings.add(('commit/' + commit[:12], 0, 'non-private commit email'))
        for entry in git('ls-tree', '-rz', commit).split(b'\0'):
            if not entry:
                continue
            info, raw_name = entry.split(b'\t', 1)
            _, kind, oid = info.split()
            name = raw_name.decode(errors='surrogateescape')
            if kind != b'blob' or (name, oid) in seen:
                continue
            seen.add((name, oid))
            blob_findings = set()
            scan(name, git('cat-file', 'blob', oid.decode()), blob_findings)
            findings.update((f'{commit[:12]}:{path}', line, rule)
                            for path, line, rule in blob_findings)
    return len(seen), len(commits)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--staged', action='store_true', help='scan the index, including staged additions')
    group.add_argument('--history', nargs='?', const='HEAD', metavar='REV',
                       help='scan every ancestral commit, blob, path and commit identity (default HEAD)')
    args = parser.parse_args()
    findings = set()
    if args.history:
        paths, commits = scan_history(args.history, findings)
        scope = f'{paths} unique path/blob pairs in {commits} commits'
    else:
        files = [name for name in git('ls-files', '-z').decode().split('\0') if name]
        for name in files:
            if args.staged:
                data = git('show', ':' + name)
            else:
                if not Path(name).is_file():
                    continue
                data = Path(name).read_bytes()
            scan(name, data, findings)
        scope = f'{len(files)} indexed paths'
    for name, line, rule in sorted(findings):
        print(f'{name}:{line}: {rule}')
    print(f'Publication scan: {len(findings)} findings across {scope}.')
    return bool(findings)


if __name__ == '__main__':
    raise SystemExit(main())
