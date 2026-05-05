#!/usr/bin/env bash
set -euo pipefail

# Quick example:
#   set -a && . ./.env && set +a
#   bash examples/ktx_reservations_example.sh

python3 scripts/ktx_booking.py reservations
