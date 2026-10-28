#!/usr/bin/env bash
# Build or serve the container image of one project, as done in docker.yml.
#
# Usage: scripts/docker.sh <build|serve> <project>
set -euo pipefail

if command -v podman >/dev/null 2>&1; then
    engine="podman"
elif command -v docker >/dev/null 2>&1; then
    engine="docker"
else
    echo "error: neither podman nor docker is installed" >&2
    exit 1
fi

if [ $# -ne 2 ]; then
    echo "Usage: $0 <build|serve> <project>" >&2
    exit 1
fi

action="$1"
project="${2%/}"
root="$(cd "$(dirname "$0")/.." && pwd)"

if [ ! -f "${root}/${project}/pixi.toml" ]; then
    echo "error: ${project}/pixi.toml not found" >&2
    exit 1
fi

case "$action" in
build)
    "$engine" build --build-arg EXAMPLE="${project}" -t "examples-${project}" "${root}"
    ;;
serve)
    "$engine" run --rm -p 5006:5006 --name "examples-${project}" "examples-${project}"
    ;;
*)
    echo "error: unknown action '${action}' (expected 'build' or 'serve')" >&2
    exit 1
    ;;
esac
