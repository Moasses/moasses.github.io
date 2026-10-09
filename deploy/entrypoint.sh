#!/bin/sh
# First start: copy the initial content into the persistent volume.
set -eu
umask 077
mkdir -p "$CONTENT_DIR" "$INSTANCE_DIR"
if [ ! -f "$CONTENT_DIR/content.json" ]; then
  cp -R /srv/app/content-seed/. "$CONTENT_DIR/"
  echo "Initial content copied to $CONTENT_DIR"
fi
mkdir -p "$CONTENT_DIR/uploads" "$CONTENT_DIR/history"
exec "$@"
