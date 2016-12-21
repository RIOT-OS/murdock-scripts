#!/bin/sh

get_apps() {
    [ -n "$APPS" ] && {
        for app in $APPS; do echo $app; done
    } || {
        dwqc -r "$REPO" -c "$COMMIT" 'find tests/ examples/ examples/iotivity_examples/ -maxdepth 1 -mindepth 1 -type d' \
            | grep -v "examples/iotivity_examples"
    }
}

get_app_board_pairs() {
    get_apps | dwqc -r "$REPO" -c "$COMMIT" \
        -s 'for board in $(make --no-print-directory -C${1} info-boards-supported 2>/dev/null ) ; do echo "BOARD=$board QUIET=0 CCACHE_BASEDIR="$(pwd)" GITCACHE_AUTO_ADD=1 RIOT_CI_BUILD=1 make -C${1} all -j4; RES=\$?; BOARD=$board make --no-print-directory -C${1} clean clean-intermediates; [ -n \"\$\(git ls-files -d\)\" ] && echo GOTCHA! && git ls-files -d ; exit \$RES ;" ; done' | $(_greplist $BOARDS)
}

jobs() {
        echo "getting jobs..." 1>&2
    [ "$STATIC_TESTS" = "1" ] && echo 'git remote add upstream https://github.com/RIOT-OS/RIOT; git fetch upstream master:master; BUILDTEST_MCU_GROUP=static-tests ./dist/tools/ci/build_and_test.sh ###{ "jobdir" : "exclusive" }'
    get_app_board_pairs
}

_greplist() {
    if [ $# -eq 0 ]; then
        echo cat
    else
        echo -n "grep -E ($1"
        shift
        for i in $*; do
            echo -n "|$i"
        done
        echo ")"
    fi
}

REPO="$1"
COMMIT="$2"

STATIC_TESTS=${STATIC_TESTS:-1}

[ -z "$REPO" -o -z "$COMMIT" ] && {
    echo "usage: $0 <repo> <commit>"
    exit 1
}

jobs | dwqc -r "$REPO" -c "$COMMIT" -P -Q -v -b -o result.json
