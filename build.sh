#!/bin/sh

get_jobs() {
    echo "getting jobs..." 1>&2
    dwqc -E APPS -E BOARDS './.murdock get_jobs'
}

export DWQ_REPO="$1"
export DWQ_COMMIT="$2"

[ -z "$DWQ_REPO" -o -z "$DWQ_COMMIT" ] && {
    echo "usage: $0 <repo> <commit>"
    exit 1
}

get_jobs | dwqc -P -Q -v -o result.json
