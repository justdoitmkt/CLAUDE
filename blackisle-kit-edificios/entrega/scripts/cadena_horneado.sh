#!/bin/bash
# Cadena de horneado final: por cada línea "ID [reuse]" de la cola ejecuta bake_apt.py, export_validate.py y los renders finales.
# La cola es un archivo de texto que se puede editar mientras corre (se lee la primera línea y se borra al empezar).
# Uso: scripts/cadena_horneado.sh <cola.txt> <bitácora.out> [carpeta de logs]      (se detiene si existe <cola.txt>.stop)
# Las líneas START / BAKE_OK / EXPORT_OK / FINAL_OK / *_FAIL de la bitácora sirven para vigilarla.
Q=$1; OUT=$2; LOGS=${3:-$(dirname "$OUT")}
PY=/root/blk-venv/bin/python
B=$(cd "$(dirname "$0")/../blender" && pwd)
cd "$B"
while true; do
  line=$(head -1 "$Q")
  if [ -z "$line" ]; then [ -f "$Q.stop" ] && break; sleep 30; continue; fi
  sed -i 1d "$Q"
  set -- $line; id=$1; flag=${2:+--$2}
  echo "START $id $flag" >> "$OUT"
  if ! $PY bake_apt.py --id $id $flag > "$LOGS/bake_$id.log" 2>&1; then echo "BAKE_FAIL $id" >> "$OUT"; tail -5 "$LOGS/bake_$id.log" >> "$OUT"; continue; fi
  echo "BAKE_OK $id" >> "$OUT"
  if $PY export_validate.py --id $id > "$LOGS/export_$id.log" 2>&1; then echo "EXPORT_OK $id" >> "$OUT"; else echo "EXPORT_FAIL $id" >> "$OUT"; tail -5 "$LOGS/export_$id.log" >> "$OUT"; fi
  if $PY tests/render_final.py --id $id --samples 48 > "$LOGS/final_$id.log" 2>&1; then echo "FINAL_OK $id" >> "$OUT"; else echo "FINAL_FAIL $id" >> "$OUT"; fi
done
echo "CHAIN_DONE" >> "$OUT"
