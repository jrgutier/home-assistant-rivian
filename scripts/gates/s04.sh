#!/usr/bin/env bash
# S4 — client cleanup.
source "$(dirname "$0")/_lib.sh"
echo "S4 — client cleanup"
on_branch "$CLIENT" vendor-client
absent "py<3.11 shims gone" '(backports[_-]strenum|async_timeout)' "$CLIENT/src"
contains "requires-python >= 3.10" '3.10' "$CLIENT/pyproject.toml"
absent "no '32-byte' phone_id docstrings" '32-byte' "$CLIENT/src"
summary S4
