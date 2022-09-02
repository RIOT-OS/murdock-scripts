#!/bin/bash

ACTION="$1"

export DWQ_DISQUE_URL="disque:7711"
CI_GIT_URL="ssh://git@git.riot-os.org:3333"
CI_GIT_URL_WORKER="https://git.riot-os.org"

MURDOCK_API_URL="http://localhost:8000"

MERGE_COMMIT_REPO="murdock/RIOT"
GITHUB_REPO_URL="https://github.com/RIOT-OS/RIOT"

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

checkout_commit() {
    local repo_dir="$1"
    local base_repo="$2"
    local base_commit="$3"

    echo "--- cloning base repo"
    git-cache init
    git-cache clone ${base_repo} ${base_commit} ${repo_dir}

    echo "--- adding remotes"
    git -C ${repo_dir} remote add cache_repo "${CI_GIT_URL}/${MERGE_COMMIT_REPO}.git"
    git -C ${repo_dir} remote add github ${GITHUB_REPO_URL}

    git -C ${repo_dir} fetch github ${base_commit}
    git -C ${repo_dir} checkout ${base_commit}
}

create_merge_commit() {
    local repo_dir="$1"
    local base_repo="$2"
    local base_head="$3"
    local pr_head="$4"
    local pr_num="$5"

    checkout_commit ${repo_dir} ${base_repo} ${base_head}

    echo "--- checking out merge branch"
    local merge_branch=pull/${base_head}/${pr_head}
    git -C ${repo_dir} checkout -B ${merge_branch}
    echo "--- fetching PR HEAD: ${pr_head}"
    git -C ${repo_dir} fetch github pull/${pr_num}/head -f
    echo "--- merging ${pr_head} into ${base_head}"
    git -C ${repo_dir} merge --no-rerere-autoupdate --no-edit --no-ff ${pr_head}
    if [ $? -ne 0 ]; then
        echo "--- creating merge commit failed, aborting!"
        rm -rf ${repo_dir}
        exit 1
    else
        echo "--- pushing result"
        git -C ${repo_dir} push --force cache_repo
    fi

    export CI_MERGE_COMMIT="$(git -C ${repo_dir} rev-parse ${merge_branch})"
    export CI_WORKER_BRANCH="${merge_branch}"
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
        export NIGHTLY STATIC_TESTS
        export DWQ_REPO="${CI_BUILD_REPO}"
        export DWQ_COMMIT="${CI_BUILD_COMMIT}"
        export DWQ_ENV="-E APPS -E BOARDS -E NIGHTLY -E STATIC_TESTS -E RUN_TESTS"

        checkout_commit ${repo_dir} ${GITHUB_REPO_URL} ${CI_BUILD_COMMIT}

        echo "--- checking out build branch"
        local build_branch=build/${CI_BUILD_COMMIT}
        git -C ${repo_dir} checkout -B ${build_branch}
        git -C ${repo_dir} log -1 --oneline
        echo "--- pushing build branch"
        git -C ${repo_dir} push --force cache_repo ${build_branch}
        echo "--- using build commit SHA1=${CI_BUILD_COMMIT}"
        echo "-- done."

        if [ -n "${CI_BUILD_BRANCH}" ]; then
            echo "-- Building branch ${CI_BUILD_BRANCH} head: ${CI_BUILD_COMMIT}..."
        elif [ -n "${CI_BUILD_TAG}" ]; then
            echo "-- Building tag ${CI_BUILD_TAG} (${CI_BUILD_COMMIT})..."
        else
            echo "-- Building commit ${CI_BUILD_COMMIT}..."
        fi
        export CI_WORKER_BRANCH="${build_branch}"
    elif [ -n "${CI_PULL_COMMIT}" ]; then
        echo "-- PR base branch is ${CI_BASE_BRANCH} at ${CI_BASE_COMMIT}"

        local actual_base_head="$(gethead ${CI_BASE_REPO} ${CI_BASE_BRANCH})"
        if [ -n "${actual_base_head}" ]; then
            if [ "${actual_base_head}" != "${CI_BASE_COMMIT}" ]; then
                echo "-- HEAD of ${CI_BASE_BRANCH} is ${actual_base_head}"
                export CI_BASE_COMMIT="${actual_base_head}"
            fi
        fi

        echo "-- merging ${CI_PULL_COMMIT} into ${CI_BASE_COMMIT}"
        create_merge_commit ${repo_dir} ${CI_BASE_REPO} ${CI_BASE_COMMIT} ${CI_PULL_COMMIT} ${CI_PULL_NR}
        echo "--- using merge commit SHA1=${CI_MERGE_COMMIT}"
        echo "-- done."

        export DWQ_REPO="${CI_GIT_URL_WORKER}/${MERGE_COMMIT_REPO}"
        export DWQ_COMMIT="${CI_MERGE_COMMIT}"

        dwqc "test -x .murdock" || {
            echo "PR does not contain .murdock build script, please rebase!"
            rm -f result.json
            exit 2
        }

        echo "-- Building PR #${CI_PULL_NR} ${CI_PULL_URL} head: ${CI_PULL_COMMIT}..."

        export DWQ_ENV="-E CI_BASE_REPO -E CI_BASE_BRANCH -E CI_PULL_REPO -E CI_PULL_COMMIT \
            -E CI_PULL_NR -E CI_PULL_URL -E CI_PULL_LABELS -E CI_MERGE_COMMIT \
            -E CI_BASE_COMMIT -E APPS -E BOARDS -E NIGHTLY -E STATIC_TESTS -E RUN_TESTS"
    else # Invalid configuration, aborting
        echo "Invalid job configuration, return with error"
        exit 2
    fi

    local report_queue="status::${CI_JOB_UID}:$(random)"
    ${BASEDIR}/reporter.py "${report_queue}" ${CI_JOB_UID} ${CI_JOB_TOKEN} &
    local reporter_pid=$!

    get_jobs | dwqc ${DWQ_ENV} \
        --maxfail 500 \
        --quiet --report ${report_queue} --outfile result.json

    local build_test_res=$?

    sleep 1

    kill ${reporter_pid} >/dev/null 2>&1 && wait ${reporter_pid} 2>/dev/null

    # Only build Doxygen documentation if the build job was successful
    if [ ${build_test_res} -eq 0 ]; then
        echo "-- Building Doxygen documentation"
        make -C ${repo_dir} doc --no-print-directory 2>/dev/null
        cp -R ${repo_dir}/doc/doxygen/html ./doc-preview
    fi

    # export result to post-build scripts
    if [ ${build_test_res} -eq 0 ]; then
        export CI_BUILD_RESULT=success
    else
        export CI_BUILD_RESULT=failed
    fi

    # run post-build.d scripts
    post_build

    if [ -n "${CI_WORKER_BRANCH}" ]; then
        echo "-- cleaning up worker branch"
        git -C ${repo_dir} push --delete cache_repo ${CI_WORKER_BRANCH}
    fi

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
