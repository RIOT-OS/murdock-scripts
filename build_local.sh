DOCKER_PID=""

trap 'echo "... TERM signal received" ; [ -n "$DOCKER_PID" ] && kill -TERM $DOCKER_PID ; exit 1' SIGTERM

export CCACHE="/data/riotbuild/bin/ccache"

_docker() {
    docker run --rm -u "$(id -u)" \
        -v "$(pwd):/data/riotbuild" \
        -v /etc/localtime:/etc/localtime:ro \
        -e 'CCACHE_BASEDIR=/data/riotbuild' \
        -e "CCACHE=${CCACHE}" \
        -e 'CCACHE_DIR=/data/ccache' \
        -e 'RIOTBASE=/data/riotbuild' \
        -e 'ENABLE_HTML=1' \
        -e "CI_PULL_LABELS=\"${CI_PULL_LABELS}\"" \
        -e "CI_PULL_NR=${CI_PULL_NR}" \
        -e "CI_BASE_BRANCH=${CI_BASE_BRANCH}" \
        -e 'GIT_CACHE_DIR=/data/gitcache' \
        -v '/home/ccache:/data/ccache' \
        -v '/srv/riot-ci/.gitcache:/data/gitcache' \
        --tmpfs '/tmp' \
        -w '/data/riotbuild' \
        --security-opt seccomp=unconfined \
        'riot/riotbuild:latest' $* &
#        'riot_ci' $* &
    DOCKER_PID=$!
    wait $DOCKER_PID
    exit $?
}
#        -e "GIT_REFERENCE=\"--reference /data/.gitcache\"" \
#        -v '/srv/riot-ci/.gitcache:/data/.gitcache' \

build() {
    mkdir bin
    cp "$CI_SCRIPTS_DIR/build_all.sh" bin
    cp "$CI_SCRIPTS_DIR/ccache" bin

    # don't use ccache if there are changes in core/include
    [ -n "$(git diff --name-only ${CI_BASE_BRANCH} -- core/include)" ] && export CCACHE=""

    _docker bin/build_all.sh
}
