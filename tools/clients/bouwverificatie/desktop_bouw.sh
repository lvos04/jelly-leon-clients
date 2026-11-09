#!/usr/bin/env bash
# Jelly Leon clients — lokale bouwverificatie van de desktop-client in een container.
#
# ALLEEN voor ontwikkeling (geen installatiemethode, niets voor de NAS). Vereist de bouwimage uit
# desktop.Dockerfile. De broncode wordt read-only gekoppeld; de compile draait zonder netwerk, met een
# CPU-/geheugenlimiet, zonder capabilities en als niet-root. Bouwt met de vendored mpvqt-bron (JLC-0001).
#
#   tools/clients/bouwverificatie/desktop_bouw.sh            # configure + build + ctest
#   JOBS=2 OUT=/tmp/desktop-bouw tools/clients/bouwverificatie/desktop_bouw.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
IMAGE="${IMAGE:-jelly-leon-clients/desktop-bouw:dev}"
OUT="${OUT:-$REPO_ROOT/.bouw/desktop}"
JOBS="${JOBS:-2}"
BUILD_TYPE="${BUILD_TYPE:-Debug}"

mkdir -p "$OUT"
if [ "$(id -u)" = "0" ]; then
  chown 568:568 "$OUT"
  RUN_AS="568:568"
else
  RUN_AS="$(id -u):$(id -g)"
fi

docker run --rm --network none --cpus "$JOBS" --memory 6g \
  --security-opt no-new-privileges --cap-drop ALL \
  --user "$RUN_AS" \
  -v "$REPO_ROOT/desktop:/src:ro" -v "$OUT:/out" \
  "$IMAGE" \
  bash -euo pipefail -c "
    cmake -S /src -B /out/build -G Ninja -DCMAKE_BUILD_TYPE=$BUILD_TYPE -DUSE_STATIC_MPVQT=ON
    cmake --build /out/build -j $JOBS
    cd /out/build && ctest --output-on-failure
  "
