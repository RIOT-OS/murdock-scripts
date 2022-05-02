#!/bin/bash -e

ACTION="$1"

export DWQ_DISQUE_URL="disque:7711"
CI_GIT_URL="ssh://git@gitea.riot-labs.de:22222"
CI_GIT_URL_WORKER="https://gitea.riot-labs.de"

MURDOCK_API_URL="http://localhost:8000"

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

    git -C "${gitdir}" ls-remote "${url}" "refs/heads/${branch}" | cut -f1
}

gethead() {
    local url="$1"
    local branch="${2:-master}"

    local gitdir="$(git rev-parse --show-toplevel 2>/dev/null)"
    [ -z "${gitdir}" ] && {
        local tmpdir="$(mktemp -d)"
        gitdir="${tmpdir}"
    }
    _gethead "${gitdir}" "${url}" "${branch}"

    local res=$?
    [ -n "${tmpdir}" ] && rm -rf "${tmpdir}"
    return ${res}
}

post_build() {
    echo "-- processing results ..."
    for script in $(find ${BASEDIR}/post-build.d -type f -executable); do
        echo "- running script \"${script}\""
        python3 ${script} || true
    done
    echo "-- done processing results"
}

get_jobs() {
    dwqc ${DWQ_ENV} './.murdock get_jobs'
}

create_merge_commit() {
    local repo_dir="$1"
    local base_repo="$2"
    local base_head="$3"
    local pr_repo="$4"
    local pr_head="$5"
    local pr_num="$6"

    echo "--- creating merge commit ..."
    echo "-- merging ${pr_head} into ${base_head}"

    local tmpdir="$(mktemp -d /tmp/murdock_git.XXXXXX)"

    local merge_branch=pull/${base_head}/${pr_head}
    set +e
    local out="$({
        set -e
        echo "--- cloning base repo"
        git-cache clone ${base_repo} ${base_head} ${repo_dir}
        git -C ${repo_dir} checkout

        echo "--- adding remotes"
        git -C ${repo_dir} remote add cache_repo "${CI_GIT_URL}/${MERGE_COMMIT_REPO}.git"
        git -C ${repo_dir} remote add pr_repo "https://github.com/${pr_repo}"

        echo "--- checking out merge branch"
        git -C ${repo_dir} checkout -B ${merge_branch}
        echo "--- fetching ${pr_head}"
        git -C ${repo_dir} fetch -f pr_repo ${pr_head}
        echo "--- merging ${pr_head} into ${base_head}"
        git -C ${repo_dir} merge --no-rerere-autoupdate --no-edit --no-ff ${pr_head} || {
            echo "--- aborting merge"
            git -C ${repo_dir} merge --abort
            rm -rf ${repo_dir}
            false
        }
        echo "--- pushing result"
        git -C ${repo_dir} push --force cache_repo
        } 2>&1 )"
    local res=$?
    set -e
    [ ${res} -ne 0 ] && {
        echo "${out}"
        echo "--- creating merge commit failed, aborting!"
        rm -rf ${repo_dir}
        exit 1
    }

    export CI_MERGE_COMMIT="$(git -C ${repo_dir} rev-parse ${merge_branch})"
    echo "--- done."
}

: ${NIGHTLY:=0}
: ${STATIC_TESTS:=0}
: ${APPS:=}
: ${BOARDS:=}

main() {
    local status='{"status" : {"status": "Fetching code"}}'
    /usr/bin/curl -s -d "${status}" -H "Content-Type: application/json" -H "Authorization: ${CI_JOB_TOKEN}" -X PUT ${MURDOCK_API_URL}/job/${CI_JOB_UID}/status > /dev/null

    export APPS BOARDS

    local repo_dir="RIOT"
    if [ -n "${CI_BUILD_COMMIT}" ]; then
        if [ -n "${CI_BUILD_BRANCH}" ]; then
            echo "-- Building branch ${CI_BUILD_BRANCH} head: ${CI_BUILD_COMMIT}..."
        elif [ -n "${CI_BUILD_TAG}" ]; then
            echo "-- Building tag ${CI_BUILD_TAG} (${CI_BUILD_COMMIT})..."
        else
            echo "-- Building commit ${CI_BUILD_COMMIT}..."
        fi

        export NIGHTLY STATIC_TESTS
        export DWQ_REPO="${CI_BUILD_REPO}"
        export DWQ_COMMIT="${CI_BUILD_COMMIT}"
        export DWQ_ENV="-E APPS -E BOARDS -E NIGHTLY -E STATIC_TESTS"
        # Clone the repository with specified commit
        git clone https://github.com/${CI_BUILD_REPO}.git ${repo_dir}
        git -C ${repo_dir} checkout ${CI_BUILD_COMMIT} 2>/dev/null
    elif [ -n "${CI_PULL_COMMIT}" ]; then
        echo "-- github reports HEAD of ${CI_BASE_BRANCH} as $CI_BASE_COMMIT"

        local actual_base_head="$(gethead ${CI_BASE_REPO} ${CI_BASE_BRANCH})"
        if [ -n "${actual_base_head}" ]; then
            if [ "${actual_base_head}" != "${CI_BASE_COMMIT}" ]; then
                echo "-- HEAD of ${CI_BASE_BRANCH} is ${actual_base_head}"
                export CI_BASE_COMMIT="${actual_base_head}"
            fi
        fi

        create_merge_commit ${repo_dir} ${CI_BASE_REPO} ${CI_BASE_COMMIT} ${CI_PULL_REPO} ${CI_PULL_COMMIT} ${CI_PULL_NR}

        export DWQ_REPO="${CI_GIT_URL_WORKER}/${MERGE_COMMIT_REPO}"
        export DWQ_COMMIT="${CI_MERGE_COMMIT}"

        echo "---- using merge commit SHA1=${CI_MERGE_COMMIT}"

        dwqc "test -x .murdock" || {
            echo "PR does not contain .murdock build script, please rebase!"
            rm -f result.json
            exit 2
        }

        echo "-- Building PR#${CI_PULL_NR} ${CI_PULL_URL} head: ${CI_PULL_COMMIT}..."

        export DWQ_ENV="-E CI_BASE_REPO -E CI_BASE_BRANCH -E CI_PULL_REPO -E CI_PULL_COMMIT \
            -E CI_PULL_NR -E CI_PULL_URL -E CI_PULL_LABELS -E CI_MERGE_COMMIT \
            -E CI_BASE_COMMIT -E APPS -E BOARDS -E NIGHTLY -E STATIC_TESTS"
    else # Invalid configuration, aborting
        echo "Invalid job configuration, return with error"
        exit 2
    fi

    local report_queue="status::${CI_JOB_UID}:$(random)"
    ${BASEDIR}/reporter.py "${report_queue}" ${CI_JOB_UID} ${CI_JOB_TOKEN} &
    local reporter_pid=$!

    set +e

    get_jobs | dwqc ${DWQ_ENV} \
        --maxfail 500 \
        --quiet --report ${report_queue} --outfile result.json

    local build_test_res=$?

    sleep 1

    kill ${reporter_pid} >/dev/null 2>&1 && wait ${reporter_pid} 2>/dev/null

    # Build Doxygen documentation
    echo "-- Building Doxygen documentation"
    make -C ${repo_dir} doc --no-print-directory 2>/dev/null
    cp -R ${repo_dir}/doc/doxygen/html ./doc-preview

    # export result to post-build scripts
    if [ ${build_test_res} -eq 0 ]; then
        export CI_BUILD_RESULT=success
    else
        export CI_BUILD_RESULT=failed
    fi

    # run post-build.d scripts
    post_build

    # remove local copy of repository
    rm -rf ${repo_dir}

    # Process result.json to generate UI data
    ${BASEDIR}/process_result.py

    echo "-- Compressing result.json"
    echo "--- Disk usage before compression: $(du -sh result.json | awk '{print $1}')"
    gzip result.json
    echo "--- Disk usage after compression : $(du -sh result.json.gz | awk '{print $1}')"
    echo "--- Total disk usage: $(du -sh . | awk '{print $1}')"

    exit ${build_test_res}
}

main
