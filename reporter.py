#!/usr/local/bin/python

import io
import json
import sys
import os
import requests
import time
import signal

from dwq import Disque, Job


sys.stdout = io.TextIOWrapper(sys.stdout.detach(), "utf-8", "replace")


def signal_handler(signal, frame):
    print(f"Exiting with signal {signal}: {frame}")
    sys.exit(0)


signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)


def has_passed(job):
    if not job:
        return False
    return job["result"]["status"] in { 0, "0", "pass" }


def job_name(job):
    return os.path.join(*job["result"]["body"]["command"].split()[1:])


def job_result_filename(job, cwd=None):
    jobname = job_name(job) + ".txt"
    filename = os.path.join("output", jobname)
    cwd = cwd or os.getcwd()
    if os.path.abspath(filename).startswith(cwd):
        return filename
    else:
        return None


def save_job_result(job):
    filename = job_result_filename(job)
    if filename:
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        with open(filename, "w") as f:
            f.write(job["result"]["output"])
        return filename


def dump_to_file(path, data):
    with open(path + ".tmp", "w") as f:
        f.write(data)
    os.rename(path + ".tmp", path)


def update_status(data, uid, failed_jobs, failed_builds, failed_tests, http_root):
    http_root = os.path.join("/", http_root)
    status = {}
    # copy expected (but optional) fields that are in data
    if data is not None:
        for f in {"total", "passed", "failed", "status", "eta"} & data.keys():
            status[f] = data[f]

    # add failed_jobs list (elements have fields "name" [required] and
    # "href" [optional]) field
    if failed_jobs:
        status["failed_jobs"] = []
        for filename, jobname in failed_jobs:
            failed_job = {"name": jobname}
            if filename:
                failed_job["href"] = os.path.join(http_root, filename)
            status["failed_jobs"].append(failed_job)

    if failed_builds:
        status["failed_builds"] = []
        for filename, jobname in failed_builds:
            failed_build = {"name": jobname.replace("compile/", "")}
            if filename:
                failed_build["href"] = os.path.join(http_root, filename)
            status["failed_builds"].append(failed_build)

    if failed_tests:
        status["failed_tests"] = []
        for filename, jobname in failed_tests:
            failed_test = {"name": jobname.replace("run_test/", "")}
            if filename:
                failed_test["href"] = os.path.join(http_root, filename)
            status["failed_tests"].append(failed_test)

    do_put_status(status, uid)


def do_put_status(status, uid):
    token = sys.argv[3]
    data = json.dumps({"uid" : uid, "status" : status})

    dump_to_file("prstatus.json", json.dumps(status, indent=True))

    requests.put(
        f'http://localhost:8000/jobs/running/{uid}/status',
        headers={"Authorization": token},
        data=data
    )


def main():
    disque_url = os.environ.get("DWQ_DISQUE_URL", "localhost:7711")
    Disque.connect([disque_url])

    http_root = os.environ.get("CI_BUILD_HTTP_ROOT", "/")

    queue = sys.argv[1]
    uid = sys.argv[2]

    last_update = 0

    maxfailed_jobs = 20
    maxfailed_builds = 20
    maxfailed_tests = 20
    failed_jobs = []
    failed_builds = []
    failed_tests = []
    nfailed_jobs = 0
    nfailed_builds = 0
    nfailed_tests = 0

    update_status({"status" : "setting up build" }, uid, [], [], [], "")

    while True:
        _list = Job.wait(queue, count=16)
        for _status in _list:
            job = _status.get('job')

            if job:
                filename = save_job_result(job)

                if filename and not has_passed(job):
                    jobname = job_name(job)
                    if jobname == "static_tests":
                        nfailed_jobs += 1
                        failed_jobs = [ (filename, jobname) ] + failed_jobs

                    elif jobname.startswith("compile/"):
                        nfailed_builds += 1
                        if nfailed_builds <= maxfailed_builds:
                            failed_builds.append((filename, job_name(job)))

                    elif jobname.startswith("run_test/"):
                        nfailed_tests += 1
                        if nfailed_tests <= maxfailed_tests:
                            failed_tests.append((filename, job_name(job)))

                    failed_jobs = failed_jobs[:maxfailed_jobs]
                    failed_builds = failed_builds[:maxfailed_builds]
                    failed_tests = failed_tests[:maxfailed_tests]

                    if nfailed_jobs > maxfailed_jobs:
                        failed_jobs.append((None, "(%s more failed jobs)" % (nfailed_jobs - maxfailed_jobs)))

                    if nfailed_builds > maxfailed_builds:
                        failed_builds.append((None, "(%s more build failures)" % (nfailed_builds - maxfailed_builds)))

                    if nfailed_tests > maxfailed_tests:
                        failed_tests.append((None, "(%s more test failures)" % (nfailed_tests - maxfailed_tests)))

            if _status.get("status", "") == "done":
                update_status(None, uid, failed_jobs, failed_builds, failed_tests, http_root)
                return

            now = time.time()
            if now - last_update > 0.5:
                update_status(_status, uid, failed_jobs, failed_builds, failed_tests, http_root)
                last_update = now


if __name__=="__main__":
    argc = len(sys.argv)
    if argc != 4:
        print(f"error: {sys.argv[0]} <queue-name> <job uid> <job token>", file=sys.stderr)
        sys.exit(1)
    main()
