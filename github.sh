# get labels of a specific PR as json list
# args: repo in "ORG/REPO" form
#       pr_num
get_pr_labels() {
    local repo=$1
    local pull_request_number=$2

    (
        echo -n "["
        get_pr_labels_raw "$repo" "$pull_request_number" | \
            grep name | tr -d '\n' | sed -e 's/\s*"name": / /g'
        echo "]"
    ) | sed -e 's/,]$/ ]/'
}

# get labels of a specific PR, raw json response
# args: repo in "ORG/REPO" form
#       pr_num
get_pr_labels_raw() {
    local repo=$1
    local pull_request_number=$2

    curl -sS "https://api.github.com/repos/${repo}/issues/${pull_request_number}/labels"
}

# get labels of a specific repository
get_repo_labels() {
    local repo=$1

    curl "https://api.github.com/repos/${repo}/labels"
}

update_CI_PULL_LABELS() {
    local repo="$1"
    local pr_num="$2"

    echo "--- updating labels for ${repo}#${pr_num}..."
    local labels="$(get_pr_labels $repo $pr_num)"
    if [ -n "$labels" ]; then
        if [ "$labels" != "[]" ]; then
            echo "-- updated PR labels:"
            echo "-- $labels"
            export CI_PULL_LABELS="$labels"
        else
            echo "warning: updating labels failed, got empty set"
        fi
    else
        echo "warning: updating labels failed!"
    fi
}

github_url_to_repo() {
    echo "$1" | sed -E 's=^https?://github\.com/==g' | sed 's/\.git$//g'
}
