#!/bin/bash
# Kit UE5: por cada línea "ID" de la cola ejecuta bake_apt.py --ue (atlas sin arena, materiales por tipo) y export_ue5.py.
# Uso: scripts/cadena_ue5.sh <cola.txt> <bitácora.out> [carpeta de logs]      (termina cuando la cola queda vacía)
Q=$1; OUT=$2; LOGS=${3:-$(dirname "$OUT")}
PY=/root/blk-venv/bin/python
B=$(cd "$(dirname "$0")/../blender" && pwd)
cd "$B"
while true; do
  id=$(head -1 "$Q" | awk '{print $1}')
  [ -z "$id" ] && break
  sed -i 1d "$Q"
  echo "START $id" >> "$OUT"
  if ! $PY bake_apt.py --id $id --ue > "$LOGS/ue_bake_$id.log" 2>&1; then echo "BAKE_FAIL $id" >> "$OUT"; tail -5 "$LOGS/ue_bake_$id.log" >> "$OUT"; continue; fi
  echo "BAKE_OK $id" >> "$OUT"
  if $PY export_ue5.py --id $id > "$LOGS/ue_export_$id.log" 2>&1; then echo "KIT_OK $id $(grep '\[ue5\]' "$LOGS/ue_export_$id.log" | cut -c1-200)" >> "$OUT"; else echo "KIT_FAIL $id" >> "$OUT"; tail -5 "$LOGS/ue_export_$id.log" >> "$OUT"; fi
done
echo "CHAIN_DONE" >> "$OUT"
