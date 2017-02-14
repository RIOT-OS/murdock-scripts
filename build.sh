#!/bin/sh -e

ACTION="$1"

# get org/repo from https://github.com/org/repo.git
repo_path() {
    local repo_url=$1
    echo $(basename $(dirname $repo_url))/$(basename $repo_url .git)
}

get_merge_commit() {
    local prnum="$1"

    local cmd="
import sys, json;
try:
    d = json.load(sys.stdin);
    m = d.get('mergeable')
    if m:
        print(d['merge_commit_sha'])
    elif m==False:
        print('False')
    else:
        print('null')
except Exception:
    print('null')
"

    wget -q -O- https://api.github.com/repos/$(repo_path $CI_BASE_REPO)/pulls/${prnum} | \
        python3 -c "$cmd"
}

wait_for_merge_commit() {
    local max=30
    local n=0
    while [ $n -lt $max ]; do
        local merge_commit_sha="$(get_merge_commit $1)"
        case "$merge_commit_sha" in
            False)
                echo "--- PR not mergeable."
                exit 1
                ;;
            null)
                echo "Waiting for merge commit sha from github... ($n sec)"
                sleep 1
                n=$(expr $n + 1)
                ;;
            *)
                [ -z "$merge_commit_sha" ] && {
                    sleep 1
                    n=$(expr $n + 1)
                    continue
                }

                export CI_MERGE_COMMIT=${merge_commit_sha}
                return
                ;;
        esac
    done

    echo "--- waited $n sec, no merge commit or not mergeable. Aborting."
    exit 1
}

get_jobs() {
    dwqc -E APPS -E BOARDS './.murdock get_jobs'
}

case "$ACTION" in
    build)
        export DWQ_REPO="$CI_BASE_REPO"
        export DWQ_COMMIT="pull/$CI_PULL_NR/merge"

        if [ -z "$CI_MERGE_COMMIT" ]; then
            wait_for_merge_commit $CI_PULL_NR
        fi

        echo "---- Merge commit SHA1=${CI_MERGE_COMMIT}"

        dwqc "test -x .murdock" || {
            echo "PR does not contain .murdock build script, please rebase!"
            rm -f result.json
            exit 2
        }

        echo "-- Building PR#$CI_PULL_NR $CI_PULL_URL head: $CI_PULL_COMMIT..."

        get_jobs | dwqc \
            -E CI_BASE_REPO -E CI_BASE_BRANCH -E CI_PULL_REPO -E CI_PULL_COMMIT \
            -E CI_PULL_NR -E CI_PULL_URL -E CI_PULL_LABELS -E CI_MERGE_COMMIT \
            --quiet --outfile result.json
        ;;
    post_build)
        {
            cat output.txt
            echo ""
            [ -s result.json ] && HTML=1 python3 /srv/murdock/murdock/parse_result.py result.json
        } | ansi2html -s solarized -u > output.html
        ;;
    *)
        echo "$0: unhandled action $ACTION"
        exit 1
        ;;
esac
