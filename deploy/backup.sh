#!/bin/sh
# ATLAS Control nightly backup (PHASE_8 Task 8.1).
# Runs INSIDE the atlas_control container via host cron:
#   docker exec atlas_control /app/deploy/backup.sh
#
# 1. Consistent SQLite snapshot via VACUUM INTO (python3 stdlib — no sqlite3 CLI in image)
# 2. Tarball (mode 600) of the snapshot + the server .env (mounted ro at /app/server.env)
# 3. Copy into the Syncthing-synced ATLAS folder 06_backups/ -> lands on the user's PC
# 4. Keep last 14 in both locations; status to /data/backups/last-backup.json
set -u

DATA_DIR="${ATLAS_DATA_DIR:-/data}"
BACKUP_DIR="$DATA_DIR/backups"
SYNC_DIR="${ATLAS_ATLAS_ROOT:-/opt/atlas}/06_backups"
DATE="$(date +%F)"
TS="$(date -u +%Y-%m-%dT%H:%M:%S+00:00)"
DB_SNAP="$BACKUP_DIR/atlas-$DATE.db"
TARBALL="$BACKUP_DIR/atlas-control-$DATE.tar.gz"

mkdir -p "$BACKUP_DIR"

fail() {
    printf '{"ts": "%s", "ok": false, "error": "%s"}\n' "$TS" "$1" > "$BACKUP_DIR/last-backup.json"
    echo "backup FAILED: $1" >&2
    exit 1
}

rm -f "$DB_SNAP"
python3 - "$DATA_DIR/atlas.db" "$DB_SNAP" <<'PYEOF' || fail "vacuum into failed"
import sqlite3, sys
src, dest = sys.argv[1], sys.argv[2]
conn = sqlite3.connect(src)
conn.execute("VACUUM INTO ?", (dest,))
conn.close()
PYEOF

# assemble tar contents in a temp dir so paths inside the tar are flat
STAGE="$(mktemp -d)"
cp "$DB_SNAP" "$STAGE/"
[ -f /app/server.env ] && cp /app/server.env "$STAGE/server.env"
tar -czf "$TARBALL" -C "$STAGE" . || { rm -rf "$STAGE"; fail "tar failed"; }
rm -rf "$STAGE"
chmod 600 "$TARBALL"

# off-box: Syncthing-synced folder (06_backups allowlisted in ATLAS .stignore)
mkdir -p "$SYNC_DIR"
cp "$TARBALL" "$SYNC_DIR/" || fail "copy to sync dir failed"

# retention: keep last 14 (by name = by date) in both locations
for dir in "$BACKUP_DIR" "$SYNC_DIR"; do
    ls -1 "$dir"/atlas-control-*.tar.gz 2>/dev/null | sort | head -n -14 | while read -r old; do
        rm -f "$old"
    done
done
ls -1 "$BACKUP_DIR"/atlas-*.db 2>/dev/null | sort | head -n -14 | while read -r old; do
    rm -f "$old"
done

SIZE="$(wc -c < "$TARBALL" | tr -d ' ')"
printf '{"ts": "%s", "ok": true, "size": %s}\n' "$TS" "$SIZE" > "$BACKUP_DIR/last-backup.json"
echo "backup OK: $TARBALL ($SIZE bytes)"
