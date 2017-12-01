#!/bin/sh -e

REPO=https://github.com/RIOT-OS/RIOT
HTTPROOT="/srv/http/ci.riot-labs.de-devel/devel"

BASEDIR="$(dirname $(realpath $0))"

. "${BASEDIR}/common.sh"

[ -f "${BASEDIR}/local.sh" ] && . "${BASEDIR}/local.sh"

main() {
    export NIGHTLY=1 STATIC_TESTS=0

    local commit="$1"
    local branch="${BRANCH:-master}"

    local output_dir="${HTTPROOT}/$(repo_path $REPO)/$branch/${commit}"

    build_commit "$REPO" "$branch" "$commit" "$output_dir" || continue
}

main "$@"
