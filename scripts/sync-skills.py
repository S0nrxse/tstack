#!/usr/bin/env python3
"""Link skills to this editable fork; optionally pull main and sync hourly."""

import argparse
import filecmp
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import tempfile


def run(*args):
    return subprocess.run(args, check=True, text=True, capture_output=True).stdout.strip()


def same_tree(left, right):
    comparison = filecmp.dircmp(left, right)
    if comparison.left_only or comparison.right_only or comparison.common_funny:
        return False
    if any(not filecmp.cmp(left / name, right / name, shallow=False)
           for name in comparison.common_files):
        return False
    return all(same_tree(left / name, right / name) for name in comparison.common_dirs)


def pull(repo):
    if run('git', '-C', str(repo), 'status', '--porcelain'):
        print('Local edits present; skipped pull. Your linked skills still use those edits.')
        return
    if run('git', '-C', str(repo), 'branch', '--show-current') != 'main':
        print('Checkout is not on main; skipped pull.')
        return
    run('git', '-C', str(repo), 'fetch', 'origin', 'main')
    run('git', '-C', str(repo), 'merge', '--ff-only', 'origin/main')


def link_skills(repo, home):
    sources = sorted(p.parent for p in (repo / 'skills').glob('*/SKILL.md'))
    if not sources:
        raise RuntimeError(f'No skills found in {repo / "skills"}')
    state_dir = home / '.local/state/tstack'
    manifest = state_dir / 'links.json'
    previous = json.loads(manifest.read_text()) if manifest.exists() else {}
    targets = {}
    for agent_home in (Path(os.environ.get('CODEX_HOME', home / '.codex')),
                       Path(os.environ.get('CLAUDE_CONFIG_DIR', home / '.claude'))):
        for source in sources:
            targets[str(agent_home / 'skills' / source.name)] = str(source)

    # Check all collisions before changing anything. Identical copied installs
    # can be adopted, but different skills and foreign symlinks stay untouched.
    for target, source in targets.items():
        dest = Path(target)
        if dest.is_symlink():
            if os.readlink(dest) != source:
                raise RuntimeError(f'Skill link already belongs to another source: {dest}')
        elif dest.exists() and (not dest.is_dir() or not same_tree(dest, Path(source))):
            raise RuntimeError(f'Existing skill differs; preserve or rename it first: {dest}')

    state_dir.mkdir(parents=True, exist_ok=True)
    backup = None
    for target, source in targets.items():
        dest = Path(target)
        if dest.is_symlink():
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            if backup is None:
                backup = Path(tempfile.mkdtemp(prefix='copies-', dir=state_dir))
            shutil.move(str(dest), str(backup / f'{dest.parent.parent.name}-{dest.name}'))
        dest.symlink_to(source, target_is_directory=True)

    # Only remove stale links previously managed by this installer.
    for target, source in previous.items():
        dest = Path(target)
        if target not in targets and dest.is_symlink() and os.readlink(dest) == source:
            dest.unlink()
    temporary = manifest.with_suffix('.tmp')
    temporary.write_text(json.dumps(targets, indent=2) + '\n')
    temporary.replace(manifest)
    print(f'Linked {len(sources)} skills for Claude Code and Codex to {repo / "skills"}.')
    if backup:
        print(f'Original identical copies backed up to {backup}.')


def systemd_quote(value):
    return '"' + str(value).replace('%', '%%').replace('\\', '\\\\').replace('"', '\\"').replace('$', '$$') + '"'


def install_auto_sync(repo, home):
    script = repo / 'scripts/sync-skills.py'
    # Preserve custom agent directories for the background job too.
    environment = {key: os.environ[key] for key in ('CODEX_HOME', 'CLAUDE_CONFIG_DIR') if key in os.environ}
    if sys.platform == 'darwin':
        agents = home / 'Library/LaunchAgents'
        agents.mkdir(parents=True, exist_ok=True)
        log = home / 'Library/Logs/tstack-sync.log'
        log.parent.mkdir(parents=True, exist_ok=True)
        plist = agents / 'com.s0nrxse.tstack-sync.plist'
        config = dict(Label='com.s0nrxse.tstack-sync',
                      ProgramArguments=[sys.executable, str(script), '--pull'],
                      StartInterval=3600, RunAtLoad=True,
                      StandardOutPath=str(log), StandardErrorPath=str(log),
                      EnvironmentVariables={'PATH': f'{home}/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin', **environment})
        plist.write_bytes(plistlib.dumps(config))
        domain = f'gui/{os.getuid()}'
        subprocess.run(['launchctl', 'bootout', domain, str(plist)], capture_output=True)
        run('launchctl', 'bootstrap', domain, str(plist))
    elif sys.platform.startswith('linux'):
        units = home / '.config/systemd/user'
        units.mkdir(parents=True, exist_ok=True)
        env_lines = ''.join(f'Environment={systemd_quote(f"{k}={v}")}\n' for k, v in environment.items())
        (units / 'tstack-sync.service').write_text(
            '[Unit]\nDescription=Sync skills from S0nrxse/tstack\n'
            '[Service]\nType=oneshot\n' + env_lines +
            f'ExecStart={systemd_quote(sys.executable)} {systemd_quote(script)} --pull\n')
        (units / 'tstack-sync.timer').write_text(
            '[Unit]\nDescription=Sync TStack skills hourly\n[Timer]\n'
            'OnBootSec=5m\nOnUnitActiveSec=1h\n[Install]\nWantedBy=timers.target\n')
        run('systemctl', '--user', 'daemon-reload')
        run('systemctl', '--user', 'enable', '--now', 'tstack-sync.timer')
    else:
        raise RuntimeError('Automatic sync supports macOS and Linux/WSL with systemd.')
    print('Hourly skill sync enabled. Software upgrades remain explicit.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pull', action='store_true', help='Fast-forward a clean main checkout from your fork')
    parser.add_argument('--install-auto-sync', action='store_true')
    args = parser.parse_args()
    repo = Path(__file__).resolve().parent.parent
    home = Path.home()
    if args.pull:
        pull(repo)
    link_skills(repo, home)
    if args.install_auto_sync:
        install_auto_sync(repo, home)


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, subprocess.CalledProcessError) as error:
        print(f'tstack sync failed: {error}', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr.strip(), file=sys.stderr)
        sys.exit(1)
