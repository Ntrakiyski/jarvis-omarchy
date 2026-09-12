"""Publication checks must catch private history even after a file is deleted."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

GUARD = Path(__file__).resolve().parents[1] / 'tools/check_public_files.py'


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.env = {**os.environ, 'GIT_AUTHOR_NAME': 'Example', 'GIT_COMMITTER_NAME': 'Example',
                    'GIT_AUTHOR_EMAIL': 'example@users.noreply.github.com',
                    'GIT_COMMITTER_EMAIL': 'example@users.noreply.github.com'}
        self.git('init', '-q')
        self.git('config', 'commit.gpgsign', 'false')
        self.git('config', 'core.hooksPath', '/dev/null')

    def git(self, *args):
        return subprocess.check_output(['git', *args], cwd=self.root, env=self.env,
                                       stderr=subprocess.STDOUT)

    def write(self, name, data):
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(data)
        self.git('add', name)

    def scan(self, *args):
        return subprocess.run(['python3', str(GUARD), *args], cwd=self.root,
                              capture_output=True, text=True, env=self.env)

    def test_deleted_transcript_remains_a_history_failure(self):
        self.write('HANDOFF.md', 'private conversation\n')
        self.git('commit', '-qm', 'Initial')
        self.git('rm', 'HANDOFF.md')
        self.write('README.md', 'Public\n')
        self.git('commit', '-qm', 'Remove transcript')
        self.assertEqual(self.scan('--staged').returncode, 0)
        result = self.scan('--history')
        self.assertEqual(result.returncode, 1)
        self.assertIn('private/runtime file', result.stdout)
        self.assertNotIn('private conversation', result.stdout)

    def test_staged_secret_cannot_be_hidden_by_clean_worktree(self):
        token = 'sk-' + 'A' * 45
        self.write('settings.txt', token)
        (self.root / 'settings.txt').write_text('clean')
        result = self.scan('--staged')
        self.assertEqual(result.returncode, 1)
        self.assertIn('OpenAI token', result.stdout)
        self.assertNotIn(token, result.stdout)

    def test_history_checks_renamed_identical_blob_paths(self):
        self.write('notes.txt', 'text')
        self.git('commit', '-qm', 'Initial')
        self.git('mv', 'notes.txt', 'HANDOFF.md')
        self.git('commit', '-qm', 'Move')
        self.assertIn('private/runtime file', self.scan('--history').stdout)

    def test_commit_message_and_identity_are_checked_without_echoing_them(self):
        self.write('README.md', 'Public')
        email = 'example' + '@' + 'gmail.com'
        self.env['GIT_AUTHOR_EMAIL'] = email
        token = 'sk-' + 'B' * 45
        self.git('commit', '-qm', token)
        result = self.scan('--history')
        self.assertEqual(result.returncode, 1)
        self.assertIn('non-private commit email', result.stdout)
        self.assertIn('OpenAI token', result.stdout)
        self.assertNotIn(email, result.stdout)
        self.assertNotIn(token, result.stdout)

    def test_clean_history_passes(self):
        self.write('README.md', 'Public documentation')
        self.git('commit', '-qm', 'Initial')
        self.assertEqual(self.scan('--history').returncode, 0)


if __name__ == '__main__':
    unittest.main()
