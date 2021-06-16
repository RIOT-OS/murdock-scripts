#!/bin/sh -e

ACTION="$1"

MERGE_COMMIT_REPO="murdock-ci/RIOT"

BASEDIR="$(dirname $(realpath $0))"

. "${BASEDIR}/common.sh"

[ -f "${BASEDIR}/local.sh" ] && . "${BASEDIR}/local.sh"

random() {
    hexdump -n ${1:-4} -e '/2 "%u"' /dev/urandom
}

retry() {
    local tries=$1
    local delay=$2
    shift 2

    local n=0
    while [ $n -lt $tries ]; do
        $1 && return 0
        $2
        sleep $delay
        n=$(expr $n + 1)
    done

    return 1
}

create_merge_commit() {
    local base_repo="$1"
    local base_head="$2"
    local pr_repo="$3"
    local pr_branch="$4"
    local pr_head="$5"
    local pr_num="$6"

    echo "--- creating merge commit ..."
    echo "-- merging $pr_head into $base_head"

    local tmpdir="$(mktemp -d /tmp/murdock_git.XXXXXX)"

    MERGE_BRANCH=pull/$base_head/$pr_head
    set +e
    OUT="$({
        set -e
        echo "--- cloning base repo"
        git-cache clone $base_repo $base_head $tmpdir
        git -C $tmpdir checkout

        echo "--- adding remotes"
        git -C $tmpdir remote add cache_repo "git@github.com:$MERGE_COMMIT_REPO"
        git -C $tmpdir remote add pr_repo "$pr_repo"

        echo "--- checking out merge branch"
        git -C $tmpdir checkout -B $MERGE_BRANCH
        echo "--- fetching $pr_branch"
        git -C $tmpdir fetch -f pr_repo $pr_branch
        echo "--- merging $pr_head into $base_head"
        git -C $tmpdir merge --no-rerere-autoupdate --no-edit --no-ff $pr_head || {
            echo "--- aborting merge"
            git -C $tmpdir merge --abort
            rm -rf $tmpdir
            false
        }
        echo "--- pushing result"
        git -C $tmpdir push --force cache_repo
        } 2>&1 )"
    RES=$?
    set -e
    [ $RES -ne 0 ] && {
        echo "$OUT"
        echo "--- creating merge commit failed, aborting!"
        rm -rf $tmpdir
        exit 1
    }

    export CI_MERGE_COMMIT="$(git -C $tmpdir rev-parse $MERGE_BRANCH)"
    rm -rf $tmpdir
    echo "--- done."
}

case "$ACTION" in
    build)
        # clean possible output
        rm -Rf output/
        rm -f prstatus.html.snip result.json

        echo "-- github reports HEAD of ${CI_BASE_BRANCH} as $CI_BASE_COMMIT"

        ACTUAL_BASE_HEAD="$(gethead ${CI_BASE_REPO} ${CI_BASE_BRANCH})"
        if [ -n "$ACTUAL_BASE_HEAD" ]; then
            if [ "$ACTUAL_BASE_HEAD" != "$CI_BASE_COMMIT" ]; then
                echo "-- HEAD of ${CI_BASE_BRANCH} is $ACTUAL_BASE_HEAD"
                export CI_BASE_COMMIT="$ACTUAL_BASE_HEAD"
            fi
        fi

        create_merge_commit $CI_BASE_REPO $CI_BASE_COMMIT $CI_PULL_REPO $CI_PULL_BRANCH $CI_PULL_COMMIT $CI_PULL_NR

        export DWQ_REPO="https://github.com/$MERGE_COMMIT_REPO"
        export DWQ_COMMIT="${CI_MERGE_COMMIT}"

        echo "---- using merge commit SHA1=${CI_MERGE_COMMIT}"

        dwqc "test -x .murdock" || {
            echo "PR does not contain .murdock build script, please rebase!"
            rm -f result.json
            exit 2
        }

        echo "-- Building PR#$CI_PULL_NR $CI_PULL_URL head: $CI_PULL_COMMIT..."

        REPORT_QUEUE="status::PR${CI_PULL_NR}:$(random)"

        $BASEDIR/parse_result.py "$REPORT_QUEUE" $CI_PULL_NR &
        REPORTER=$!

        set +e

        get_jobs | dwqc \
            -E CI_BASE_REPO -E CI_BASE_BRANCH -E CI_PULL_REPO -E CI_PULL_COMMIT \
            -E CI_PULL_NR -E CI_PULL_URL -E CI_PULL_LABELS -E CI_MERGE_COMMIT \
            -E CI_BASE_COMMIT \
            --maxfail 500 \
            --quiet --report $REPORT_QUEUE --outfile result.json

        RES=$?

        sleep 1

        kill $REPORTER >/dev/null 2>&1 && wait $REPORTER 2>/dev/null

        # export result to post-build scripts
        if [ $RES -eq 0 ]; then
            export CI_BUILD_RESULT=success
        else
            export CI_BUILD_RESULT=failed
        fi

        # run post-build.d scripts
        post_build

        exit $RES
        ;;
    post_build)
        {
            cat output.txt
            echo ""
            [ -s result.json ] && HTML=1 ${BASEDIR}/parse_result.py result.json
        } | ansi2html -s solarized -u > output.html

        ${BASEDIR}/parse_result.py static result.json output.txt
        ;;
    *)
        echo "$0: unhandled action $ACTION"
        exit 1
        ;;
esac
