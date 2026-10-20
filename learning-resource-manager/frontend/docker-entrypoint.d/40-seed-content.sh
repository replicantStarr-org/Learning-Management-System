#!/bin/sh
set -eu

# Local Compose already bind-mounts the library. Only cloud replicas need seeds.
[ "${SEED_CONTENT:-false}" = true ] || exit 0

# This marker belongs to the volume, not the container: restarting nginx must
# not resurrect seed PDFs that a reader has deliberately deleted.
[ ! -f /content/.seeded ] || exit 0
mkdir -p /content/pdf
# Preserve uploads and tolerate a retry after an interrupted first copy.
cp -n /opt/resource-seed/pdf/*.pdf /content/pdf/
touch /content/.seeded
