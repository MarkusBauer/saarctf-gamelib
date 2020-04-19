#!/usr/bin/env bash
set -euxo pipefail

SCRIPTPATH="$(cd "$(dirname "$BASH_SOURCE")" && pwd)"

# Docker only - install systemd handler, remove the rest
if [ -f /.dockerenv ]; then
	cp /opt/gamelib/ci/docker-systemd/* /opt/
	rm -rf /opt/gamelib /opt/service
	rm -rf /tmp/*
fi
