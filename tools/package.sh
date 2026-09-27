#!/usr/bin/env bash
# Package the rebuilt SKSE plugin DLLs as a FOMOD override zip, installable
# AFTER the base Mantella mod in MO2 / Amethyst (or any manager that extracts
# a plain zip: the payload sits at the archive root either way).
#
#   tools/package.sh            # zip -> ~/Téléchargements/
#
# Overridable env: WORK= OUTDIR= VERSION=
set -euo pipefail

REPO=$(cd "$(dirname "$0")/.." && pwd)
WORK=${WORK:-/tmp/mantella-build}
OUTDIR=${OUTDIR:-$HOME/Téléchargements}
VERSION=${VERSION:-$(date +%Y%m%d)}
NAME=Mantella-AE1.7.104-SKSE-Plugins-fixed

STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT

mkdir -p "$STAGE/fomod" "$STAGE/SKSE/Plugins" "$OUTDIR"
cp "$REPO/fomod/ModuleConfig.xml" "$STAGE/fomod/"
[ -f "$REPO/fomod/info.xml" ] && cp "$REPO/fomod/info.xml" "$STAGE/fomod/"

for dll in SKSE_HTTP MantellaDialogue MantellaLauncher MantellaSubtitles; do
    src=$(find "$WORK/out" -maxdepth 1 -name "$dll.dll" | head -1)
    [ -n "$src" ] || { echo "FATAL: $dll.dll not built (run tools/build.sh first)"; exit 1; }
    cp "$src" "$STAGE/SKSE/Plugins/"
done

ZIP="$OUTDIR/$NAME.zip"
rm -f "$ZIP"
(cd "$STAGE" && zip -qr "$ZIP" .)

# Assert every FOMOD `source=` is an actual FILE in the archive. A directory
# reference (or a typo) is not an error for Amethyst's installer — it silently
# copies "0 item(s)" and then fails on the missing staging dir. Found this the
# hard way: a ModuleConfig with <file source="SKSE" destination="SKSE"/>.
fomod_bad=0
for src in $(grep -o 'source="[^"]*"' "$REPO/fomod/ModuleConfig.xml" | sed 's/source="//;s/"$//' | sort -u); do
    if [ ! -f "$STAGE/$src" ]; then
        echo "FATAL: fomod source is missing or not a regular file: $src"
        fomod_bad=1
    fi
done
[ "$fomod_bad" -eq 0 ] || exit 1

# Assert the layout instead of trusting it: every entry must sit under fomod/
# or SKSE/, which is exactly what both the FOMOD parser and a dumb unzip see.
bad=$(unzip -Z1 "$ZIP" | grep -Ev '^(fomod/|SKSE/|$)' || true)
if [ -n "$bad" ]; then
    echo "FATAL: unexpected archive entries:"; echo "$bad"; exit 1
fi

{
    echo "# $NAME"
    echo "Built: $(date -Iseconds)"
    echo
    echo "| file | sha256 |"
    echo "|---|---|"
    (cd "$STAGE" && find . -type f -name '*.dll' | sort | xargs sha256sum) | awk '{print "| " $2 " | " $1 " |"}'
    echo
    echo "zip: $(sha256sum "$ZIP" | cut -d' ' -f1)  ($ZIP)"
} >> "$REPO/research/shipping.md"

unzip -l "$ZIP"
echo
echo "OK: $ZIP"
