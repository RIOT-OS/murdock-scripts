#!/bin/bash

trap 'echo "... SIGTERM" ; cleanup ; exit 1' SIGTERM

TMP_DIR=$(mktemp -d build_out.XXXXXX)

cleanup() {
    rm -Rf -- "${TMP_DIR}"
}

ALL_GROUPS="static-tests cortex_m4_3 cortex_m4_2 cortex_m4_1 cortex_m0_2 cortex_m0_1 x86 cortex_m3_2 cortex_m3_1 avr8 msp430 arm7"
#ALL_GROUPS="static-tests avr8" # cortex_m4_2 cortex_m4_1 cortex_m0_2 cortex_m0_1 x86 cortex_m3_2 cortex_m3_1 avr8 msp430 arm7"

NPROC=${NPROC:-8}
export NPROC

html_anchor() {
    [ -z "$ENABLE_HTML" ] && return
    echo "<a name=\"$1\"></a>"
}

html_link() {
    if [ -z "$ENABLE_HTML" ]; then
        echo $1
    else
        echo "<a href=\"#$1\">$1</a>"
    fi
}

build_group() {
    BUILD_GROUP=$1
    echo "Building group $BUILD_GROUP..."
    local script=./dist/tools/ci/build_and_test.sh
    [ ! -f "$script" } && script=./dist/tools/travis-scripts/build_and_test.sh

    cp -a pkg pkg_${BUILD_GROUP}

    BUILDTEST_MCU_GROUP=$BUILD_GROUP \
    RIOT_VERSION_OVERRIDE=buildtest \
    BUILDTEST_NO_REBASE=1 \
    RIOTPKG=$(pwd)/pkg_${BUILD_GROUP} \
    $script > ${TMP_DIR}/${BUILD_GROUP} 2>&1

    RES=$?
    if [ $RES -eq 0 ]; then
        true
        #rm ${TMP_DIR}/${BUILD_GROUP}
    else
        echo $BUILD_GROUP >> ${TMP_DIR}/error
    fi

    echo "Build group $BUILD_GROUP done."
    return $RES
}

echo ""
echo ""
[ -n "$ENABLE_HTML" ] && html_link "RESULTS"
echo ""
echo ""

[ -z "$CCACHE" ] && echo "$0: ccache disabled."

BUILD_GROUPS="${1-$ALL_GROUPS}"

#if [[ "$BUILD_GROUPS" =~ .*static-tests.* ]]; then
#    build_group static-tests
#fi

for group in $BUILD_GROUPS; do
    build_group $group &
done

wait

html_anchor RESULTS

if [ -f ${TMP_DIR}/error ]; then
    echo ""
    echo "The following build groups had errors:"
    for group in $(cat ${TMP_DIR}/error); do
        html_link $group
    done
    echo ""
else
    echo ""
    echo "ALL BUILDGROUPS COMPLETED WITHOUT ERRORS."
    echo ""
fi

for output in $(ls ${TMP_DIR}); do
    [ "$output" = "error" ] && continue
    echo ""
    html_anchor $output
    echo "BUILD OUTPUT of group $(basename $output):"
    cat ${TMP_DIR}/$output
done

echo ""

if [ -f ${TMP_DIR}/error ]; then
    echo ""
    echo "Build failed!"
    cleanup
    exit 1
else
    echo "Build succeeded."
    cleanup
    exit 0
fi
