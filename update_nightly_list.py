#! /usr/bin/env python3

import argparse
import datetime
import json
import os
import re
import time

FILENAME = "nightlies.json"


def find_commit_build(builds, commit):
    for build in builds:
        if build["commit"] == commit:
            return build
    return None


def main(repodir, branch="master"):
    nightly_file = os.path.join(repodir, branch, FILENAME)
    try:
        # parse existing list file
        with open(nightly_file) as f:
            nightly = json.load(f)
    except:
        # there is no list file at the moment or a different error happened
        # just try to create a new one
        nightly = []
    branch_dir = os.path.join(repodir, branch)
    # get hash of latest commit from symlink
    latest_commit = os.path.realpath(os.path.join(branch_dir, "latest"))\
        .split(os.path.sep)[-1]
    # check if it was already build in a previous build
    build = find_commit_build(nightly, latest_commit)
    if build is None:
        build = {"commit": latest_commit}
    else:
        # remove so it is definitely at the beginning later
        nightly.remove(build)
    with open(os.path.join(branch_dir, "latest", "output.html")) as f:
        c = re.compile(r"--- result: BUILD SUCCESSFUL\.")
        build["result"] = "errored"
        for line in f:
            if c.match(line) is not None:
                build["result"] = "passed"
                break
    build["since"] = time.mktime(datetime.datetime.now().timetuple())
    # add latest build on top
    nightly.insert(0, build)
    # restrict number of builds to 7 (one week ideally)
    nightly = nightly[:7]
    with open(nightly_file, "w") as f:
        json.dump(nightly, f, indent=" "*4)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument(
            "repodir",
            help="Web directory for the repo the nightlies are build for"
        )
    p.add_argument(
            "branch",
            help="Last build branch of the nightlies",
            default="master",
            nargs="?"
        )
    main(**vars(p.parse_args()))
