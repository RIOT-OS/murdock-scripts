#!/bin/sh -e

REPO=https://github.com/RIOT-OS/RIOT
BRANCHES="master"
HTTPROOT="/srv/http/ci.riot-labs.de-devel/devel"

BASEDIR="$(dirname $(realpath $0))"

. "${BASEDIR}/common.sh"

[ -f "${BASEDIR}/local.sh" ] && . "${BASEDIR}/local.sh"

main() {
    export NIGHTLY=1 STATIC_TESTS=0

    for branch in $BRANCHES; do
        local commit="$(gethead $REPO $branch)"
        local output_dir="${HTTPROOT}/$(repo_path $REPO)/$branch/${commit}"

        [ -d "$output_dir" ] && {
            echo "--- $REPO $branch $commit:"
            echo "    $output_dir exists. skipping."
            continue
        }

        mkdir -p "$output_dir"

        build $REPO $branch $commit $output_dir | tee $output_dir/output.txt && \
        {
            cd $output_dir
            cat output.txt
            echo ""
            [ -s result.json ] && HTML=1 ${BASEDIR}/parse_result.py result.json
        } | ansi2html -s solarized -u > ${output_dir}/output.html

        local latest_link="$(dirname "$output_dir")/latest"
        rm -f "$latest_link"
        ln -s "$output_dir" "$latest_link"
    done
}

main
