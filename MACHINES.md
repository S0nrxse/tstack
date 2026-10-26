# Peyton's machines

## Using daFleet

Our devices now keep this fork inside one daFleet checkout, at `daFleet/tstack`.
Use daFleet's bootstrap and `~/.local/bin/fleet update` for device access and
skill synchronization. This replaces the separate checkout and timer described
in the standalone setup below. Do not run both sync systems on the same account.

Edit skills under `daFleet/tstack/skills`. Push the changed commit to this fork,
then commit and push the new `tstack` submodule revision in the parent daFleet
repo. Other devices receive that pinned revision with their hourly fleet update.
Local edits and unpublished child commits stop updates instead of being discarded.
Each device keeps its own SSH and repository credentials outside both repos.

The `dafleet` agent skill explains how to find other devices and use `fleet ssh`.
See the parent repo's `docs/access-setup.md` and `docs/agent-setup.md` for current
enrollment and software status. The standalone instructions below remain useful
for machines that do not use daFleet.

## Standalone installation

This fork is the source for our Claude Code and Codex skills. Each machine uses
an editable checkout at `~/src/tstack`. Both agents link to that checkout, so an
edit takes effect locally immediately. Hourly sync fast-forwards clean `main`
checkouts from **S0nrxse/tstack**, never from upstream. Local edits, other branches,
and diverged commits are not overwritten. Unrelated installed skills are left alone.

## Set up a machine

On **macOS, Linux, or WSL** with `git`, `curl`, and `python3` installed:

```bash
curl -fsSL https://raw.githubusercontent.com/S0nrxse/tstack/main/scripts/setup.sh -o /tmp/tstack-setup.sh
bash /tmp/tstack-setup.sh
claude auth login
```

The setup installs the official T3 **nightly** CLI and the official Claude Code
native build. It does not restart running servers. Claude updates itself; run
`t3 update --channel nightly` to update T3 when ready to restart it. This avoids
interrupting active work through an unattended software upgrade.

For the desktop UI, install **T3 Code Nightly** from
[the official download page](https://t3.codes/download). The desktop app is a
separate installation from the `t3` CLI. Update the desktop before switching an
existing remote server to nightly: incompatible app/server versions cannot connect.
On Intel Macs, use the nightly desktop app; the official standalone T3 CLI does
not currently publish an Intel Mac archive.

Authenticate Claude separately on every machine. In T3 Code, open
**Settings → Providers**, refresh Claude, and select it when starting a thread.
For remote projects, install and authenticate Claude on the remote server.
No login credentials are copied between machines or committed to this repo.

The bootstrap does not install or authenticate `gh`; the TStack PR skills need
an authenticated [GitHub CLI](https://cli.github.com/). `council` and `sol-loop`
also need the multi-provider delegation support described in the README.

## Edit and share skills

```bash
cd ~/src/tstack
# Edit skills/<name>/SKILL.md (or edit the symlink in either agent's skills folder).
git add skills
git commit -m "Adjust my skills"
git push origin main
```

Other online machines pick up the change within an hour, provided their checkout
is clean and on `main`. New agent sessions pick up changed skills. To sync now:

```bash
python3 ~/src/tstack/scripts/sync-skills.py --pull
```

Linux uses a user systemd timer, which needs systemd enabled in WSL and an active
user manager. For a headless server, user lingering keeps it active after logout.
macOS uses a LaunchAgent that runs while you are logged in. Offline machines
sync when they are back online and the next job runs. Re-running setup is safe.
Custom `CODEX_HOME` and `CLAUDE_CONFIG_DIR` directories are supported.

## Inspect or stop automatic sync

Linux:

```bash
systemctl --user list-timers tstack-sync.timer
journalctl --user -u tstack-sync.service -n 20
systemctl --user disable --now tstack-sync.timer
```

macOS:

```bash
tail -20 ~/Library/Logs/tstack-sync.log
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.s0nrxse.tstack-sync.plist
```

Identical preexisting copied skills are backed up under `~/.local/state/tstack/`
before becoming links. A conflicting skill or link stops setup for you to resolve.
To bring in upstream changes, add `t3dotgg/tstack` as the `upstream` remote, merge
the changes you want into your fork, and push. Upstream changes are never pulled
automatically.
