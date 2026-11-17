#!/usr/bin/env bash
# Setargan-Darya root launcher: the real project lives in swim02/ —
# just forward there, so running from EITHER folder gives the same result.
exec "$(dirname "$0")/swim02/run.sh" "$@"
