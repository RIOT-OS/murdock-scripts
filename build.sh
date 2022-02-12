#!/bin/sh -e

ACTION="$1"

CI_GIT_URL="ssh://git@gitea.riot-labs.de:22222"
CI_GIT_URL_WORKER="https://gitea.riot-labs.de"

MERGE_COMMIT_REPO="riot-ci/RIOT"

BASEDIR="$(dirname $(realpath $0))"

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

_gethead() {
    local gitdir="$1"
    local url="$2"
    local branch="${3:-master}"

    git -C "$gitdir" ls-remote "$url" "refs/heads/${branch}" | cut -f1
}

gethead() {
    local url="$1"
    local branch="${2:-master}"

    local gitdir="$(git rev-parse --show-toplevel 2>/dev/null)"
    [ -z "$gitdir" ] && {
        local tmpdir="$(mktemp -d)"
        gitdir="$tmpdir"
    }
    _gethead "$gitdir" "$url" "$branch"

    RES=$?
    [ -n "$tmpdir" ] && rm -rf "$tmpdir"
    return $RES
}

post_build() {
    echo "-- processing results ..."
    for script in $(find ${BASEDIR}/post-build.d -type f -executable); do
        echo "- running script \"$script\""
        python ${script} || true
    done
    echo "-- done processing results"
}

get_jobs() {
    dwqc ${DWQ_ENV} './.murdock get_jobs'
}

create_merge_commit() {
    local base_repo="$1"
    local base_head="$2"
    local pr_repo="$3"
    local pr_head="$4"
    local pr_num="$5"

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
        git -C $tmpdir remote add cache_repo "${CI_GIT_URL}/${MERGE_COMMIT_REPO}.git"
        git -C $tmpdir remote add pr_repo "https://github.com/$pr_repo"

        echo "--- checking out merge branch"
        git -C $tmpdir checkout -B $MERGE_BRANCH
        echo "--- fetching $pr_head"
        git -C $tmpdir fetch -f pr_repo $pr_head
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
    run)
        # clean possible output
        rm -Rf output/
        rm -f prstatus.html.snip result.json

        STATUS='{"status" : {"status": "Fetching code"}}'
        /usr/bin/curl -s -d "${STATUS}" -H "Content-Type: application/json" -H "Authorization: ${CI_JOB_TOKEN}" -X PUT http://localhost:8000/jobs/running/${CI_JOB_UID}/status > /dev/null

        : ${NIGHTLY:=0}
        : ${STATIC_TESTS:=0}
        : ${APPS:=}
        : ${BOARDS:=}

        export APPS BOARDS

        if [ -n "${CI_BUILD_COMMIT}" ]; then
            if [ -n "${CI_BUILD_BRANCH}" ]; then
                echo "-- Building branch ${CI_BUILD_BRANCH} head: ${CI_BUILD_COMMIT}..."
                QUEUE_NAME=${CI_BUILD_BRANCH}${CI_BUILD_COMMIT}
                # Create a symlink to this job so it can be linked easily in an URL
                mkdir -p ../branches
                rm -f ../branches/${CI_BUILD_BRANCH}
                ln -s ${PWD} ../branches/${CI_BUILD_BRANCH}
            elif [ -n "${CI_BUILD_TAG}" ]; then
                echo "-- Building tag ${CI_BUILD_TAG} (${CI_BUILD_COMMIT})..."
                QUEUE_NAME=${CI_BUILD_TAG}${CI_BUILD_COMMIT}
                # Create a symlink to this job so it can be linked easily in an URL
                mkdir -p ../tags
                rm -f ../tags/${CI_BUILD_TAG}
                ln -s ${PWD} ../tags/${CI_BUILD_TAG}
            else
                echo "-- Building commit ${CI_BUILD_COMMIT}..."
                QUEUE_NAME=${CI_BUILD_COMMIT}
            fi

            REPORT_QUEUE="status::${QUEUE_NAME}:$(random)"
            export NIGHTLY STATIC_TESTS
            export DWQ_REPO="${CI_BUILD_REPO}"
            export DWQ_COMMIT="${CI_BUILD_COMMIT}"
            export DWQ_ENV="-E APPS -E BOARDS -E NIGHTLY -E STATIC_TESTS"
        else # Building a PR

            echo "-- github reports HEAD of ${CI_BASE_BRANCH} as $CI_BASE_COMMIT"

            ACTUAL_BASE_HEAD="$(gethead ${CI_BASE_REPO} ${CI_BASE_BRANCH})"
            if [ -n "$ACTUAL_BASE_HEAD" ]; then
                if [ "$ACTUAL_BASE_HEAD" != "$CI_BASE_COMMIT" ]; then
                    echo "-- HEAD of ${CI_BASE_BRANCH} is $ACTUAL_BASE_HEAD"
                    export CI_BASE_COMMIT="$ACTUAL_BASE_HEAD"
                fi
            fi

            create_merge_commit $CI_BASE_REPO $CI_BASE_COMMIT $CI_PULL_REPO $CI_PULL_COMMIT $CI_PULL_NR

            export DWQ_REPO="${CI_GIT_URL_WORKER}/${MERGE_COMMIT_REPO}"
            export DWQ_COMMIT="${CI_MERGE_COMMIT}"

            echo "---- using merge commit SHA1=${CI_MERGE_COMMIT}"

            dwqc "test -x .murdock" || {
                echo "PR does not contain .murdock build script, please rebase!"
                rm -f result.json
                exit 2
            }

            echo "-- Building PR#$CI_PULL_NR $CI_PULL_URL head: $CI_PULL_COMMIT..."

            export DWQ_ENV="-E CI_BASE_REPO -E CI_BASE_BRANCH -E CI_PULL_REPO -E CI_PULL_COMMIT \
                -E CI_PULL_NR -E CI_PULL_URL -E CI_PULL_LABELS -E CI_MERGE_COMMIT \
                -E CI_BASE_COMMIT -E APPS -E BOARDS -E NIGHTLY -E STATIC_TESTS"

            REPORT_QUEUE="status::PR${CI_PULL_NR}:$(random)"
        fi

        python $BASEDIR/reporter.py "$REPORT_QUEUE" $CI_JOB_UID $CI_JOB_TOKEN &
        REPORTER=$!

        set +e

        get_jobs | dwqc ${DWQ_ENV} \
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
    finalize)
        python ${BASEDIR}/process_result.py
        ;;
    *)
        echo "$0: unhandled action $ACTION"
        exit 1
        ;;
esac
