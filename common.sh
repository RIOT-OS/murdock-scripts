# get org/repo from https://github.com/org/repo.git
repo_path() {
    local repo_url=$1
    echo $(basename $(dirname $repo_url))/$(basename $repo_url .git)
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
        $script || true
    done
    echo "-- done processing results"
}

get_jobs() {
    dwqc -E NIGHTLY -E STATIC_TESTS -E APPS -E BOARDS './.murdock get_jobs'
}

build() {
    local repo="$1"
    local branch="$2"
    local commit="$3"
    local output_dir="$4"

    export DWQ_REPO="$repo"
    export DWQ_COMMIT="$commit"

    echo "--- Building branch \"$branch\" from repo \"$repo\""
    echo "-- HEAD commit is \"$DWQ_COMMIT\""

    echo "-- using output directory \"$output_dir\""

    mkdir -p "$output_dir"
    cd "$output_dir"

    echo "-- sanity checking build cluster ..."
    dwqc "test -x .murdock" || {
        echo "-- failed! aborting..."
        rm -f result.json
        return 2
    } && echo "-- ok."

    echo "-- starting build..."

    set +e

    get_jobs | dwqc \
        -E NIGHTLY \
        --quiet --maxfail 500 --outfile result.json

    RES=$?

    set -e

    if [ $RES -eq 0 ]; then
        echo "-- done. Build succeeded."
    else
        echo "-- done. Build failed."
    fi

    export repo branch commit output_dir
    post_build

    return
}

build_commit() {
    local repo="$1"
    local branch="$2"
    local commit="$3"
    local output_dir="$4"

    [ -d "$output_dir" ] && {
        echo "--- $repo $branch $commit:"
        echo "    $output_dir exists. skipping."
        return 1
    }

    mkdir -p "$output_dir"

    build $repo $branch $commit $output_dir | tee $output_dir/output.txt && \
    {
        cd $output_dir
        cat output.txt
        echo ""
        [ -s result.json ] && HTML=1 ${BASEDIR}/parse_result.py result.json
    } | ansi2html -s solarized -u > ${output_dir}/output.html
}
