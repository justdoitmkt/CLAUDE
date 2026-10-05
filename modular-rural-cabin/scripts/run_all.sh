#!/usr/bin/env bash
# Full pipeline: UE 4.22 project zip -> GLBs. Needs Python 3.11 with bpy==5.0.1, numpy, pillow.
# Usage: KIT_WORK=/path/to/work ./run_all.sh /path/to/Modular_Rural_Cabin.zip
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
export KIT_WORK="${KIT_WORK:-/home/user/work2}"
PY="${PY:-python}"
mkdir -p "$KIT_WORK/src" "$KIT_WORK/build"
[ -d "$KIT_WORK/src/Modular Rural Cabin" ] || unzip -q "$1" -d "$KIT_WORK/src"
cd "$HERE"
$PY ue_tex.py                                                    # 273 texture sources, lossless PNG
ls "$KIT_WORK/src/Modular Rural Cabin/Materials/Instances" | sed 's/\.uasset$//' \
  | xargs -P 3 -n 4 $PY bake_materials.py                        # 97 material instances
$PY bake_special.py                                              # per-mesh bakes (caravan, pier, boat, diorama)
$PY build_glb.py                                                 # 155 meshes + Blueprint assemblies + cabins
find "$KIT_WORK/glb" -name '*.glb' -print0 | xargs -0 $PY fix_tangents.py
$PY audit_glb.py
$PY catalog.py
