import io
import json
import sys
import os
import requests
import time
import signal
import argparse

from dwq import Disque, Job

from common import parse_job


sys.stdout = io.TextIOWrapper(sys.stdout.detach(), "utf-8", "replace")


def signal_handler(signal, frame):
    print(f"Exiting with signal {signal}: {frame}")
    sys.exit(0)


signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)


def save_job_result(job):
    filename = os.path.join("output", f"{job['name']}.txt")
    if filename:
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        with open(filename, "w") as f:
            f.write(job["output"])
        return filename


def update_status(data, uid, token, failed_jobs, failed_builds, failed_tests, http_root):
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
        for jobname in failed_jobs:
            failed_job = {"name": jobname}
            status["failed_jobs"].append(failed_job)

    if failed_builds:
        status["failed_builds"] = []
        for application, board, toolchain, worker, runtime  in failed_builds:
            failed_build = {
                "application": application,
                "board": board,
                "toolchain": toolchain,
                "worker": worker,
                "runtime": runtime,
            }
            status["failed_builds"].append(failed_build)

    if failed_tests:
        status["failed_tests"] = []
        for application, board, toolchain, worker, runtime  in failed_tests:
            failed_test = {
                "application": application,
                "board": board,
                "toolchain": toolchain,
                "worker": worker,
                "runtime": runtime,
            }
            status["failed_tests"].append(failed_test)

    data = json.dumps({"uid" : uid, "status" : status})
    requests.put(
        f'http://localhost:8000/jobs/running/{uid}/status',
        headers={"Authorization": token},
        data=data
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("queue", type=str, help="Name of the queue to listen to")
    parser.add_argument("job_uid", type=str, help="UID of the Murdock job")
    parser.add_argument("job_token", type=str, help="Authentication token of the Murdock job")
    args = parser.parse_args()
    queue = args.queue
    uid = args.job_uid
    token = args.job_token

    disque_url = os.environ.get("DWQ_DISQUE_URL", "localhost:7711")
    Disque.connect([disque_url])

    http_root = os.environ.get("CI_BUILD_HTTP_ROOT", "/")

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

    update_status({"status" : "setting up build" }, uid, token, [], [], [], "")

    while True:
        _list = Job.wait(queue, count=16)
        for _status in _list:
            job_raw = _status.get('job')

            if job_raw:
                job = parse_job(job_raw)
                filename = save_job_result(job)

                if filename and job["status"] is False:
                    jobname = job["name"]
                    worker = job["worker"]
                    runtime = job["runtime"]
                    if jobname == "static_tests":
                        nfailed_jobs += 1
                        failed_jobs.append(jobname)

                    elif jobname.startswith("compile/"):
                        nfailed_builds += 1
                        if nfailed_builds <= maxfailed_builds:
                            failed_builds.append(
                                (job["application"], job["board"], job["toolchain"], worker, runtime)
                            )

                    elif jobname.startswith("run_test/"):
                        nfailed_tests += 1
                        if nfailed_tests <= maxfailed_tests:
                            failed_tests.append(
                                (job["application"], job["board"], job["toolchain"], worker, runtime)
                            )

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
                update_status(None, uid, token, failed_jobs, failed_builds, failed_tests, http_root)
                return

            now = time.time()
            if now - last_update > 0.5:
                update_status(_status, uid, token, failed_jobs, failed_builds, failed_tests, http_root)
                last_update = now


if __name__=="__main__":
    main()
