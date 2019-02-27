#!/bin/sh -e

REPO=https://github.com/RIOT-OS/RIOT
BRANCHES="master"
HTTPROOT="/srv/http/ci.riot-labs.de-devel/devel"

BASEDIR="$(dirname $(realpath $0))"

. "${BASEDIR}/common.sh"

[ -f "${BASEDIR}/local.sh" ] && . "${BASEDIR}/local.sh"

REPO_DIR="${HTTPROOT}/$(repo_path ${REPO})"

main() {
    export NIGHTLY=1 STATIC_TESTS=0 SAVE_JOB_RESULTS=1

    for branch in $BRANCHES; do
        local commit="$(gethead $REPO $branch)"
        local output_dir="${REPO_DIR}/$branch/${commit}"

        build_commit "$REPO" "$branch" "$commit" "$output_dir" || continue

        local latest_link="$(dirname "$output_dir")/latest"
        ln -s -f -T "$output_dir" "$latest_link" || true

        # generate JSON so it can be fetched by the web frontend
        ${BASEDIR}/update_nightly_list.py ${REPO_DIR} ${branch}
    done
}

main
