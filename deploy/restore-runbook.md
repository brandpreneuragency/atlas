# ATLAS Control — restore runbook

How to restore the SQLite database (and server `.env`) into a fresh container
from a nightly backup tarball. Backups live in two places:

- On the VPS: docker volume `atlas_control_data`, path `/data/backups/atlas-control-<date>.tar.gz`
- Off-box: `~/atlas/06_backups/atlas-control-<date>.tar.gz` on the user's PC (via Syncthing;
  server-side source is `/home/admin/atlas/06_backups/`)

Each tarball contains `atlas-<date>.db` (a `VACUUM INTO` snapshot — a complete,
consistent database) and `server.env` (the container env file, mode 600).

## Restore steps

All commands as `admin` on the VPS.

1. **Stop the app** (do NOT touch the `hermes` container):

   ```sh
   cd /home/admin/atlas-control
   docker-compose -f deploy/docker-compose.yml stop atlas_control
   ```

2. **Pick a backup** (from the volume, or copy one back from your PC to the server first):

   ```sh
   docker run --rm -v atlas_control_data:/data alpine ls -la /data/backups
   ```

3. **Unpack and swap the database in the volume** (example date shown):

   ```sh
   docker run --rm -v atlas_control_data:/data alpine sh -c '
     cd /data &&
     tar -xzf backups/atlas-control-2026-07-06.tar.gz -C /tmp &&
     mv atlas.db atlas.db.pre-restore 2>/dev/null;
     cp /tmp/atlas-2026-07-06.db /data/atlas.db &&
     rm -f /data/atlas.db-wal /data/atlas.db-shm &&
     ls -la /data'
   ```

   Removing `-wal`/`-shm` is required: they belong to the old database.

4. **Restore `.env` if lost** (skip when `/home/admin/atlas-control/.env` still exists):

   ```sh
   docker run --rm -v atlas_control_data:/data alpine sh -c '
     tar -xzf /data/backups/atlas-control-2026-07-06.tar.gz -C /tmp ./server.env &&
     cat /tmp/server.env' > /home/admin/atlas-control/.env
   chmod 600 /home/admin/atlas-control/.env
   ```

5. **Start and verify:**

   ```sh
   docker-compose -f deploy/docker-compose.yml up -d
   curl -sf https://atlas.brandpreneur.net/api/health
   ```

   Expect `{"status":"ok","db":"ok",...}`. Log in and check the event feed
   renders history from the restored DB. Runs that were `running` at backup
   time will show `failed: interrupted by restart` — that is the engine's
   normal restart recovery.

6. **Clean up** `atlas.db.pre-restore` once satisfied.

## Fresh-server restore (nothing but the tarball)

1. Clone the repo to `/home/admin/atlas-control`, restore `.env` from the tarball (step 4).
2. `docker network create atlas_net` if missing; connect `hermes` + `tabs_caddy_1`.
3. `docker-compose -f deploy/docker-compose.yml up -d` once (creates the volume), then steps 1–5.
