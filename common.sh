# get org/repo from https://github.com/org/repo.git
repo_path() {
    local repo_url=$1
    echo $(basename $(dirname $repo_url))/$(basename $repo_url .git)
}

_gethead() {
    local gitdir="$1"
    local url="$2"
    local branch="${3:-master}"

    git -C "$gitdir" ls-remote "$url" "${branch}" | cut -f1
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
    exit $RES
}
