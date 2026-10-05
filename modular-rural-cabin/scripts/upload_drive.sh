#!/usr/bin/env bash
# Upload the generated GLBs to Google Drive: Assets/Modular Rural Cabin GLB/<subfolders>.
# Needs a Drive OAuth token in the environment (never in the repo or the chat):
#   RCLONE_CONFIG_GDRIVE_TYPE=drive
#   RCLONE_CONFIG_GDRIVE_SCOPE=drive
#   RCLONE_CONFIG_GDRIVE_TOKEN={"access_token":...,"refresh_token":...}   (from `rclone authorize "drive"`)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
export KIT_WORK="${KIT_WORK:-/home/user/work2}"
ASSETS_FOLDER_ID="${ASSETS_FOLDER_ID:-1ae5dzruxfaxWmtpk-7nTySklXk2zZ38R}"   # Drive folder "Assets"
DEST="gdrive:Modular Rural Cabin GLB"
command -v rclone >/dev/null || pip install -q rclone-bin
: "${RCLONE_CONFIG_GDRIVE_TOKEN:?Drive token missing (RCLONE_CONFIG_GDRIVE_TOKEN)}"
rclone copy "$KIT_WORK/glb" "$DEST" --drive-root-folder-id "$ASSETS_FOLDER_ID" --transfers 4 --checksum --stats 30s --stats-one-line
rclone copy "$HERE/.." "$DEST" --drive-root-folder-id "$ASSETS_FOLDER_ID" --include "README.md" --include "MODELOS.md" --include "previews/**"
rclone check "$KIT_WORK/glb" "$DEST" --drive-root-folder-id "$ASSETS_FOLDER_ID" --one-way
