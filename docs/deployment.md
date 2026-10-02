# Deploying project-tracker

This guide installs project-tracker on an Ubuntu 24.04 server, where it runs
under systemd with Gunicorn. It also covers updating, backups, rolling back,
and reading the logs. Every command can be pasted as-is. Each one has a
one-line explanation, and every step ends with a check that it worked.

> [!WARNING]
> **Keep it on your home network.** project-tracker has no login. Anyone who
> can reach the port can read, change, and delete your projects. Use it only
> from your LAN and your tailnet. **Never** forward the port on your router,
> and **never** expose it with Tailscale Funnel.

## How it is laid out

| What | Where | Owned by |
| --- | --- | --- |
| Code and virtual environment (venv) | `/opt/project-tracker` | your login user (read-only for the service) |
| Settings and secret key | `/etc/project-tracker/project-tracker.env` | `root`, readable by the `project-tracker` group |
| Database | `/var/lib/project-tracker/project_tracker.db` | `project-tracker` system user |
| Backups | `/var/backups/project-tracker/` | `root` only |
| Service definition | `/etc/systemd/system/project-tracker.service` | `root` |
| Logs | the systemd journal (`journalctl -u project-tracker`) | — |

The app listens on port **8002** on all of the server's addresses (`0.0.0.0`),
so the LAN and the tailnet can both reach it.

The commands below use `sudo` for anything that changes the system. Run them
from your own login account, not as root. `git` and `pip` run as your own
user and never with `sudo`. The database commands run as the service's
`project-tracker` user, via `sudo -u project-tracker`.

---

## 1. First install

### 1.1 Check the port is free

```bash
# List listening TCP ports and the programs that own them, and keep only port 8002
sudo ss -tlnp | grep ':8002 '
```

**Verify:** no output means nothing is using port 8002 yet. If a line appears,
something else already uses the port. Stop here and pick another port; you
will set it as `PROJECT_TRACKER_PORT` in step 1.6.

### 1.2 Install the system packages

```bash
# Install git (to fetch the code), the Python venv module, sqlite3 (for backups) and curl (for checks)
sudo apt update && sudo apt install -y git python3-venv sqlite3 curl
```

**Verify:**

```bash
# Each line should print a version; Python must be 3.12.x
git --version; python3 --version; sqlite3 --version; curl --version | head -1
```

### 1.3 Create the service user

```bash
# Create a system user and group called project-tracker, with no password, no home directory and no login shell
sudo adduser --system --group project-tracker
```

**Verify:**

```bash
# Shows the user's IDs and group; the shell at the end should be /usr/sbin/nologin
id project-tracker && getent passwd project-tracker
```

### 1.4 Create the directories

```bash
# Code directory, owned by you so git and pip don't need sudo
sudo install -d -o "$USER" -g "$USER" -m 0755 /opt/project-tracker

# Database directory: only the service user can write to it, other users can't read it
sudo install -d -o project-tracker -g project-tracker -m 0750 /var/lib/project-tracker

# Settings directory for the environment file
sudo install -d -o root -g root -m 0755 /etc/project-tracker

# Backup directory, readable by root only
sudo install -d -o root -g root -m 0700 /var/backups/project-tracker
```

**Verify:**

```bash
# Shows each directory's owner, group and permissions
sudo ls -ld /opt/project-tracker /var/lib/project-tracker /etc/project-tracker /var/backups/project-tracker
```

Expect your username on `/opt/project-tracker`, `project-tracker project-tracker`
on `/var/lib/project-tracker`, and `root root` on the other two.

### 1.5 Get the code and install it

```bash
# Download the code into /opt/project-tracker
git clone https://github.com/jmabes/project-tracker.git /opt/project-tracker

# Create the virtual environment inside the checkout
python3 -m venv /opt/project-tracker/.venv

# Install the app's runtime packages (not the development tools) into the venv
/opt/project-tracker/.venv/bin/python -m pip install -r /opt/project-tracker/requirements.txt
```

If the `venv` step fails with "ensurepip is not available", step 1.2 didn't
install `python3-venv`. Run step 1.2 again, delete the partial venv with
`rm -rf /opt/project-tracker/.venv`, then run the `venv` step again.

**Verify:**

```bash
# Shows the commit you are on, and the installed Gunicorn version
git -C /opt/project-tracker log -1 --oneline && /opt/project-tracker/.venv/bin/gunicorn --version
```

### 1.6 Create the environment file

This file holds the secret key and the database location. The service reads
it at start-up. It is created empty with tight permissions first, so the
secret is never readable by other users, not even briefly.

```bash
# Create an empty file that only root can write and only the project-tracker group can read
sudo install -o root -g project-tracker -m 0640 /dev/null /etc/project-tracker/project-tracker.env

# Generate a random secret key and write all settings into the file
printf '%s\n' \
  'PROJECT_TRACKER_CONFIG=production' \
  "SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex())')" \
  'DATABASE_URL=sqlite:////var/lib/project-tracker/project_tracker.db' \
  'PROJECT_TRACKER_HOST=0.0.0.0' \
  'PROJECT_TRACKER_PORT=8002' \
  | sudo tee /etc/project-tracker/project-tracker.env > /dev/null
```

**Verify:**

```bash
# Shows the permissions (-rw-r----- root project-tracker) and the setting names, but not the secret's value
sudo ls -l /etc/project-tracker/project-tracker.env && sudo cut -d= -f1 /etc/project-tracker/project-tracker.env
```

You should see five names: `PROJECT_TRACKER_CONFIG`, `SECRET_KEY`,
`DATABASE_URL`, `PROJECT_TRACKER_HOST` and `PROJECT_TRACKER_PORT`.

- Never share or commit this file. If the secret key leaks, see
  [Changing the secret key](#changing-the-secret-key).
- `DATABASE_URL` has **four** slashes after `sqlite:`. Three belong to the
  URL and the fourth starts the absolute path `/var/lib/...`.

### 1.7 Create the database

This creates the database file and its tables. It runs as the service user,
so the file gets the right owner, and it loads the environment file you just
wrote.

```bash
# Create or upgrade the database tables, running as project-tracker with the production settings
sudo -u project-tracker bash -c 'set -a && . /etc/project-tracker/project-tracker.env && set +a && cd /opt/project-tracker && .venv/bin/flask --app project_tracker db upgrade'
```

You'll see a few `INFO [alembic...] Running upgrade ...` lines.

**Verify:**

```bash
# Shows the file's owner (project-tracker) and lists its tables (alembic_version and projects)
sudo ls -l /var/lib/project-tracker/ && sudo sqlite3 /var/lib/project-tracker/project_tracker.db '.tables'
```

### 1.8 Install and start the service

```bash
# Copy the service definition into systemd's directory
sudo cp /opt/project-tracker/deploy/project-tracker.service /etc/systemd/system/project-tracker.service

# Check the service file for mistakes (no output means it's fine)
sudo systemd-analyze verify /etc/systemd/system/project-tracker.service

# Tell systemd to re-read its service files
sudo systemctl daemon-reload

# Start the service now, and at every boot
sudo systemctl enable --now project-tracker
```

**Verify:**

```bash
# Should say "Active: active (running)" and show the gunicorn processes running as project-tracker
systemctl status project-tracker --no-pager
```

```bash
# Should print "enabled" (starts at boot) and then "active" (running now)
systemctl is-enabled project-tracker; systemctl is-active project-tracker
```

```bash
# Ask the app whether it can reach its database; should print {"status":"ok"} and HTTP 200
curl -sS -w '\nHTTP %{http_code}\n' http://127.0.0.1:8002/healthz
```

```bash
# Shows that Gunicorn is listening on 0.0.0.0:8002
sudo ss -tlnp | grep ':8002 '
```

### 1.9 Check it from another machine

On the server, find its addresses:

```bash
# The server's LAN address(es), e.g. 192.168.1.20
hostname -I

# The server's tailnet address (100.x.y.z), if Tailscale is installed
tailscale ip -4
```

From **another computer on your LAN**, replace `<server-ip>` with the LAN
address:

```bash
# Should print {"status":"ok"} and HTTP 200
curl -sS -w '\nHTTP %{http_code}\n' http://<server-ip>:8002/healthz
```

Then open `http://<server-ip>:8002/` in a browser. From a device on your
tailnet, use the server's `100.x.y.z` address or its MagicDNS name instead.

If the curl works on the server but not from another machine, a firewall is
probably blocking it. Check whether Ubuntu's firewall is on:

```bash
# Prints "Status: inactive" (nothing to do) or "Status: active" plus the rules
sudo ufw status
```

Only if it says **active**, allow port 8002 from your LAN and your tailnet,
and from nowhere else. Change `192.168.1.0/24` to match your LAN: the first
three numbers of the address from `hostname -I`, followed by `.0/24`.

```bash
# Allow the LAN to reach port 8002
sudo ufw allow from 192.168.1.0/24 to any port 8002 proto tcp

# Allow tailnet devices (they arrive on the tailscale0 interface) to reach port 8002
sudo ufw allow in on tailscale0 to any port 8002 proto tcp
```

**Verify:** `sudo ufw status` lists the two new rules, and the curl above now
works from the other machine.

---

## 2. Updating to a new version

Each update takes a backup first and writes down the current commit, so you
can [roll back](#4-rolling-back-to-a-previous-version) if something goes
wrong.

```bash
# 1. Back up the database (see section 3.1 for details)
sudo sqlite3 /var/lib/project-tracker/project_tracker.db ".timeout 5000" ".backup '/var/backups/project-tracker/project_tracker-$(date +%Y%m%d-%H%M%S).db'"

# 2. Save the current commit ID to a file in your home directory, for a rollback
git -C /opt/project-tracker rev-parse HEAD | tee ~/project-tracker-previous-commit

# 3. Download the new version (refuses to run if you have local changes)
git -C /opt/project-tracker pull --ff-only

# 4. Install any new or changed packages
/opt/project-tracker/.venv/bin/python -m pip install -r /opt/project-tracker/requirements.txt

# 5. Stop the app so the database isn't in use while its tables change
sudo systemctl stop project-tracker

# 6. Apply any database changes
sudo -u project-tracker bash -c 'set -a && . /etc/project-tracker/project-tracker.env && set +a && cd /opt/project-tracker && .venv/bin/flask --app project_tracker db upgrade'

# 7. Install the service file again, in case the update changed it (harmless if not)
sudo cp /opt/project-tracker/deploy/project-tracker.service /etc/systemd/system/project-tracker.service && sudo systemctl daemon-reload

# 8. Start the app again
sudo systemctl start project-tracker
```

**Verify:**

```bash
# The new commit is checked out
git -C /opt/project-tracker log -1 --oneline

# The service is running, and the app can reach its database (HTTP 200)
systemctl is-active project-tracker && curl -sS -w '\nHTTP %{http_code}\n' http://127.0.0.1:8002/healthz
```

Open the app in a browser and check your projects are still there. The
database lives in `/var/lib/project-tracker`, outside the code checkout, so
`git pull` never touches it.

---

## 3. Backup and restore

The database is a single SQLite file. **Don't copy it with `cp` while the app
is running.** A copy taken mid-write can be corrupt. Use SQLite's `.backup`
command instead: it makes a consistent copy even while the app is in use.

### 3.1 Take a backup

```bash
# Make a consistent copy of the live database, named with today's date and time
sudo sqlite3 /var/lib/project-tracker/project_tracker.db ".timeout 5000" ".backup '/var/backups/project-tracker/project_tracker-$(date +%Y%m%d-%H%M%S).db'"
```

`.timeout 5000` lets the backup wait up to 5 seconds if the app is writing at
that moment.

**Verify:**

```bash
# List the backups, newest first
sudo ls -lt /var/backups/project-tracker/
```

```bash
# Check the newest backup: should print "ok" and then the number of projects in it
sudo sqlite3 "$(sudo sh -c 'ls -t /var/backups/project-tracker/*.db | head -1')" 'PRAGMA integrity_check;' 'SELECT count(*) FROM projects;'
```

The part inside `"$(...)"` finds the newest backup. It runs through
`sudo sh -c` because only root can list the backup directory.

Backups on the same disk don't protect you from a dead disk. Now and then,
copy `/var/backups/project-tracker/` to another machine.

### 3.2 Restore a backup

This replaces **all** current data with the backup's contents. Anything
added or changed after that backup was taken is lost.

```bash
# 1. List the backups and pick one (copy its full name)
sudo ls -lt /var/backups/project-tracker/

# 2. Stop the app so nothing writes while the data is replaced
sudo systemctl stop project-tracker

# 3. Back up the current data first, in case you change your mind
sudo sqlite3 /var/lib/project-tracker/project_tracker.db ".backup '/var/backups/project-tracker/project_tracker-before-restore-$(date +%Y%m%d-%H%M%S).db'"

# 4. Replace the database contents with the backup (change the file name to the one you picked)
sudo sqlite3 /var/lib/project-tracker/project_tracker.db ".restore '/var/backups/project-tracker/project_tracker-YYYYMMDD-HHMMSS.db'"

# 5. Make sure the service user still owns the database file
sudo chown project-tracker:project-tracker /var/lib/project-tracker/project_tracker.db

# 6. Start the app again
sudo systemctl start project-tracker
```

**Verify:**

```bash
# Should print "ok" and the number of projects you expect from that backup
sudo sqlite3 /var/lib/project-tracker/project_tracker.db 'PRAGMA integrity_check;' 'SELECT count(*) FROM projects;'

# The service is running, and the app can reach its database (HTTP 200)
systemctl is-active project-tracker && curl -sS -w '\nHTTP %{http_code}\n' http://127.0.0.1:8002/healthz
```

If you restore a backup taken before an update that changed the database,
run the `flask db upgrade` command from [step 6 of updating](#2-updating-to-a-new-version)
before starting the app.

---

## 4. Rolling back to a previous version

Use this if an update broke something. It puts back the code from before the
update and, if the update changed the database, the backup taken just before
it.

```bash
# 1. Show the commit you were on before the last update (saved by step 2 of updating)
cat ~/project-tracker-previous-commit

# 2. Show what the update changed in the database layout (empty output = no database changes)
git -C /opt/project-tracker diff --stat "$(cat ~/project-tracker-previous-commit)" HEAD -- migrations/

# 3. Stop the app
sudo systemctl stop project-tracker

# 4. Switch the code back to the previous commit
git -C /opt/project-tracker checkout "$(cat ~/project-tracker-previous-commit)"

# 5. Reinstall that version's packages
/opt/project-tracker/.venv/bin/python -m pip install -r /opt/project-tracker/requirements.txt

# 6. Reinstall that version's service file
sudo cp /opt/project-tracker/deploy/project-tracker.service /etc/systemd/system/project-tracker.service && sudo systemctl daemon-reload
```

**Only if step 2 printed something**, the newer version changed the database,
and the older code can't use it. Restore the backup from step 1 of the update,
which is the newest backup taken before that update, using steps 3–5 of
[Restore a backup](#32-restore-a-backup). Changes you made after the update
are lost. If step 2 printed nothing, skip this and keep your current data.

```bash
# 7. Start the app again
sudo systemctl start project-tracker
```

**Verify:**

```bash
# Shows the commit you rolled back to (same ID as step 1), "HEAD detached at ..." is expected
git -C /opt/project-tracker status | head -1 && git -C /opt/project-tracker log -1 --oneline

# The service is running, and the app can reach its database (HTTP 200)
systemctl is-active project-tracker && curl -sS -w '\nHTTP %{http_code}\n' http://127.0.0.1:8002/healthz
```

The checkout is now "detached" at the old commit, so `git pull` won't work.
When a fixed version is out, go back to the main branch and then follow
[Updating](#2-updating-to-a-new-version):

```bash
# Return to the main branch (then follow section 2 as usual)
git -C /opt/project-tracker checkout main
```

**Verify:** `git -C /opt/project-tracker status | head -1` prints `On branch main`.

---

## 5. Logs and troubleshooting

Gunicorn writes its access log (one line per request) and its error log to
the systemd journal.

```bash
# The last 50 log lines
sudo journalctl -u project-tracker -n 50 --no-pager

# Follow new log lines live (press Ctrl+C to stop)
sudo journalctl -u project-tracker -f

# Everything since the last boot
sudo journalctl -u project-tracker -b --no-pager

# Only the last hour
sudo journalctl -u project-tracker --since "1 hour ago" --no-pager

# Only errors
sudo journalctl -u project-tracker -p err --no-pager
```

**Verify:** run `curl http://127.0.0.1:8002/healthz`, then the first command.
The last line should be a `"GET /healthz HTTP/1.1" 200` access-log entry.

### "SECRET_KEY must be set in production" or "DATABASE_URL must be set in production"

In production the app refuses to start without both settings, so it never
runs with a guessable key or a database in the wrong place. In the journal
this looks like:

```text
[ERROR] Exception in worker process
...
RuntimeError: SECRET_KEY must be set in production
...
[ERROR] Worker (pid:1234) exited with code 3.
[ERROR] Shutting down: Master
[ERROR] Reason: Worker failed to boot.
```

`systemctl status project-tracker` shows `activating (auto-restart)`, and
systemd retries every 5 seconds. To fix it:

```bash
# Show the setting names in the environment file; all five from step 1.6 must be there
sudo cut -d= -f1 /etc/project-tracker/project-tracker.env
```

If one is missing or empty, redo [step 1.6](#16-create-the-environment-file)
(it is safe to repeat; see [Changing the secret key](#changing-the-secret-key)),
then restart:

```bash
# Restart the service so it re-reads the environment file
sudo systemctl restart project-tracker
```

**Verify:** `systemctl is-active project-tracker` prints `active`, and the
`/healthz` curl returns HTTP 200.

### `/healthz` returns HTTP 503

The app is running but can't read its database. The journal has the detail
(look for `Health check database query failed`):

```bash
# Show recent errors, including the database error message
sudo journalctl -u project-tracker -p err -n 30 --no-pager
```

Common causes:

- **`unable to open database file`:** `DATABASE_URL` points at the wrong
  place (check the four slashes), or the database directory or file isn't
  owned by `project-tracker`. Check with
  `sudo ls -l /var/lib/project-tracker/`. Fix the ownership with
  `sudo chown -R project-tracker:project-tracker /var/lib/project-tracker`.
- **`no such table: projects`:** the database exists but has no tables.
  Either the `flask db upgrade` step was skipped, or `DATABASE_URL` points at
  a different, empty file. Run [step 1.7](#17-create-the-database) again.

After fixing it, restart with `sudo systemctl restart project-tracker`.

**Verify:** the `/healthz` curl returns HTTP 200.

### The service keeps restarting

```bash
# Show the service state and its last log lines
systemctl status project-tracker --no-pager
```

Read the error in the journal (see above). `Address already in use` means
another program took port 8002. Find it with `sudo ss -tlnp | grep ':8002 '`,
then either stop that program or change `PROJECT_TRACKER_PORT` in the
environment file and restart.

### Changing the secret key

The secret key signs form submissions. Changing it is safe; it only
invalidates forms that are open in a browser at that moment. To generate a
new one, repeat [step 1.6](#16-create-the-environment-file), then restart:

```bash
# Restart so the new key is used
sudo systemctl restart project-tracker
```

**Verify:** `systemctl is-active project-tracker` prints `active`.

### How the service is sandboxed

The service file uses systemd's sandboxing. The app can write only to
`/var/lib/project-tracker`. It sees the rest of the system, including its own
code, as read-only, and it can't see home directories at all. To see what
the sandbox restricts:

```bash
# Score the service's sandboxing (lower is safer; "OK" is expected)
systemd-analyze security project-tracker --no-pager | tail -1
```
