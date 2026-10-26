#!/usr/bin/env python3
"""Integration checks for shared installs and preserving edits during sync."""

import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('sync', Path(__file__).with_name('sync-skills.py'))
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / 'home'
        self.repo = self.root / 'checkout'
        self.source = self.repo / 'skills/demo'
        self.source.mkdir(parents=True)
        (self.source / 'SKILL.md').write_text('original')
        self.dest = self.home / '.codex/skills/demo'
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, {'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null'}).start()
        for key in ('CODEX_HOME', 'CLAUDE_CONFIG_DIR'):
            patch.dict(os.environ, {key: str(self.home / ('.codex' if key == 'CODEX_HOME' else '.claude'))}).start()

    def git(self, *args, at=None):
        return sync.run('git', '-C', str(at or self.repo), *args)

    def commit(self, message):
        self.git('add', '.')
        self.git('-c', 'user.name=Test', '-c', 'user.email=test@example.com', 'commit', '-m', message)

    def remote(self):
        self.git('init', '-b', 'main')
        self.commit('initial')
        remote = self.root / 'remote.git'
        sync.run('git', 'clone', '--bare', str(self.repo), str(remote))
        self.git('remote', 'add', 'origin', str(remote))
        return remote

    def test_shared_edits_idempotency_and_unrelated_skills(self):
        unrelated = self.home / '.claude/skills/custom/SKILL.md'
        unrelated.parent.mkdir(parents=True)
        unrelated.write_text('keep me')
        sync.link_skills(self.repo, self.home)
        sync.link_skills(self.repo, self.home)
        (self.dest / 'SKILL.md').write_text('edited')
        self.assertEqual((self.source / 'SKILL.md').read_text(), 'edited')
        self.assertEqual((self.home / '.claude/skills/demo/SKILL.md').read_text(), 'edited')
        self.assertEqual(unrelated.read_text(), 'keep me')

    def test_adopt_identical_copy_with_backup(self):
        shutil.copytree(self.source, self.dest)
        sync.link_skills(self.repo, self.home)
        self.assertTrue(self.dest.is_symlink())
        self.assertEqual(len(list((self.home / '.local/state/tstack').glob('copies-*'))), 1)

    def test_conflicts_fail_before_any_install(self):
        self.dest.mkdir(parents=True)
        (self.dest / 'SKILL.md').write_text('personal version')
        with self.assertRaises(RuntimeError):
            sync.link_skills(self.repo, self.home)
        self.assertEqual((self.dest / 'SKILL.md').read_text(), 'personal version')
        self.assertFalse((self.home / '.claude/skills/demo').exists())

    def test_foreign_symlink_untouched(self):
        self.dest.parent.mkdir(parents=True)
        self.dest.symlink_to(self.root / 'foreign')
        with self.assertRaises(RuntimeError):
            sync.link_skills(self.repo, self.home)
        self.assertEqual(os.readlink(self.dest), str(self.root / 'foreign'))

    def test_remove_only_our_stale_links(self):
        sync.link_skills(self.repo, self.home)
        self.source.rename(self.source.with_name('renamed'))
        sync.link_skills(self.repo, self.home)
        self.assertFalse(self.dest.is_symlink())
        self.assertTrue(self.dest.with_name('renamed').is_symlink())

    def test_fast_forward_and_preserve_dirty_branch(self):
        remote = self.remote()
        writer = self.root / 'writer'
        sync.run('git', 'clone', str(remote), str(writer))
        skill = writer / 'skills/demo/SKILL.md'
        skill.write_text('published')
        self.git('add', '.', at=writer)
        self.git('-c', 'user.name=Test', '-c', 'user.email=test@example.com', 'commit', '-m', 'published', at=writer)
        self.git('push', 'origin', 'main', at=writer)
        (self.source / 'SKILL.md').write_text('local edits')
        sync.pull(self.repo)
        self.assertEqual((self.source / 'SKILL.md').read_text(), 'local edits')
        self.git('restore', 'skills/demo/SKILL.md')
        self.git('switch', '-c', 'work')
        sync.pull(self.repo)
        self.assertEqual((self.source / 'SKILL.md').read_text(), 'original')
        self.git('switch', 'main')
        sync.pull(self.repo)
        self.assertEqual((self.source / 'SKILL.md').read_text(), 'published')

    def test_divergence_is_never_reset(self):
        remote = self.remote()
        (self.source / 'SKILL.md').write_text('local commit')
        self.commit('local')
        before = self.git('rev-parse', 'HEAD')
        writer = self.root / 'writer'
        sync.run('git', 'clone', str(remote), str(writer))
        (writer / 'another-file').write_text('published')
        self.git('add', '.', at=writer)
        self.git('-c', 'user.name=Test', '-c', 'user.email=test@example.com', 'commit', '-m', 'published', at=writer)
        self.git('push', 'origin', 'main', at=writer)
        with self.assertRaises(subprocess.CalledProcessError):
            sync.pull(self.repo)
        self.assertEqual(self.git('rev-parse', 'HEAD'), before)
        self.assertEqual((self.source / 'SKILL.md').read_text(), 'local commit')


if __name__ == '__main__':
    unittest.main()
