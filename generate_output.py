#!/usr/bin/env python3

import json
import sys
import os
import requests
import time
import re
import shutil

from multiprocessing import Manager
from concurrent.futures import ProcessPoolExecutor

import minify_html
from jinja2 import FileSystemLoader, Environment
from dwq import Disque, Job


DISQUE_URL = "localhost:7711"

OUTPUT_DIR = os.path.abspath(os.getcwd())
HTML_DIR = os.path.join(OUTPUT_DIR, "html")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(SCRIPT_DIR, "templates")

MURDOCK_CTRL_URL = os.getenv(
    "MURDOCK_CTRL_URL", "http://localhost:3000/control"
)
HTTP_ROOT = os.getenv("CI_BUILD_HTTP_ROOT", "")
LOCAL_TESTING = int(os.getenv("LOCAL_TESTING", "0")) == 1
BASE_URL = os.getenv(
    "BASE_URL",
    OUTPUT_DIR if LOCAL_TESTING else "https://ci.riot-os.org/RIOT-OS/RIOT"
)

PULL_NR = os.getenv("CI_PULL_NR")
PULL_COMMIT = os.getenv("CI_PULL_COMMIT")
BUILD_BRANCH = os.getenv("BUILD_BRANCH")
BUILD_COMMIT = os.getenv("BUILD_COMMIT")

MAX_WORKERS = int(os.getenv("MAX_WORKERS", 8))
MAX_FAILED_DISPLAYED = 20
SAVE_JOB_RESULTS = int(os.getenv("SAVE_JOB_RESULTS", "0")) == 1


def parse_job(job):
    result = {}
    result["id"] = job["job_id"]
    result["status"] = job["result"]["status"] in { 0, "0", "pass" }
    result["output"] = job["result"]["output"]
    result["worker"] = job["result"]["worker"]
    result["runtime"] = job["result"]["runtime"]
    result["name"] = os.path.join(
        *job["result"]["body"]["command"].split()[1:]
    )
    match = re.match(
        r"./.murdock ([a-z_]+) ([a-zA-Z0-9/\-_]+) ([a-zA-Z0-9_\-]+):([a-z]+)",
        job["result"]["body"]["command"]
    )
    if match is not None:
        result["type"] = match.group(1)
        result["application"] = match.group(2)
        result["board"] = match.group(3)
        result["toolchain"] = match.group(4)
    elif result["name"] == "static-test":
        result["type"] = result["name"]
    return result


def parse_all_jobs(jobs):
    build_applications = {
        job["application"]: [] for job in jobs if job["type"] == "compile"
    }
    build_application_success = {
        application: [] for application in build_applications
    }
    build_application_failures = {
        application: [] for application in build_applications
    }
    test_applications = {
        job["application"]: [] for job in jobs if job["type"] == "run_test"
    }
    test_application_success = {
        application: [] for application in test_applications
    }
    test_application_failures = {
        application: [] for application in test_applications
    }
    workers_runtimes = {}
    builds_count = 0
    build_success_count = 0
    build_failures_count = 0
    tests_count = 0
    test_success_count = 0
    test_failures_count = 0
    for job in jobs:
        application = job["application"]
        worker = job["worker"]
        if job["type"] == "compile":
            builds_count += 1
            build_applications[application].append(job)
            if worker not in workers_runtimes:
                workers_runtimes.update({worker: []})
            workers_runtimes[worker].append(job["runtime"])
            if job["status"] is False:
                build_failures_count += 1
                build_application_failures[application].append(job)
            else:
                build_success_count += 1
                build_application_success[application].append(job)
            continue
        if job["type"] == "run_test":
            tests_count += 1
            test_applications[application].append(job)
            if job["status"] is False:
                test_failures_count += 1
                test_application_failures[application].append(job)
            else:
                test_success_count += 1
                test_application_success[application].append(job)

    total_build_time = time.gmtime(sum([
        sum(runtimes) for _, runtimes in workers_runtimes.items()
    ]))

    jobs_count = builds_count + tests_count
    errors = build_failures_count + test_failures_count
    status = "failed" if not jobs_count or errors else "passed"

    return {
        "status": status,
        "jobs_count": jobs_count,
        "builds": build_applications,
        "builds_count": builds_count,
        "build_success": build_application_success,
        "build_success_count": build_success_count,
        "build_failures": build_application_failures,
        "build_failures_count": build_failures_count,
        "tests": test_applications,
        "tests_count": tests_count,
        "test_success": test_application_success,
        "test_failures": test_application_failures,
        "test_success_count": test_success_count,
        "test_failures_count": test_failures_count,
        "workers": sorted(workers_runtimes.keys()),
        "workers_runtimes": workers_runtimes,
        "total_time": time.strftime(r"%dd %Hh %Mm %Ss", total_build_time),
    }


def store_job_output(job):
    output_path = os.path.join(
        OUTPUT_DIR, "output", job["type"], job["application"]
    )
    os.makedirs(output_path, exist_ok=True)
    output_filename = os.path.join(
        output_path, "{board}:{toolchain}.txt".format(**job)
    )
    with open(output_filename, "w") as f:
        f.write(job["output"])
    return output_filename


def _render_template(context, template):
    loader = FileSystemLoader(searchpath=TEMPLATES_DIR)
    env = Environment(
        loader=loader, trim_blocks=True, lstrip_blocks=True,
        keep_trailing_newline=True
    )
    env.globals.update(zip=zip)
    template = env.get_template(template)
    render = template.render(**context)
    try:
        return minify_html.minify(render, minify_js=False, minify_css=False)
    except SyntaxError as e:
        print(template, e)
        return render


def render_main_page(context):
    if not os.path.exists(HTML_DIR):
        os.makedirs(HTML_DIR)
    filepath = os.path.join(HTML_DIR, "index.html")
    with open(filepath, "w") as f:
        f.write(_render_template(context, "index.html.j2"))


def render_application_page(application, job_type, context):
    filename = os.path.join(HTML_DIR, job_type, "{}.html".format(application))
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, "w") as f:
        f.write(_render_template(context, "application.html.j2"))


def create_application_output(app, jobs, job_type, failures, context):
    application_context = {
        "status": "failed" if failures else "passed",
        "base_url": context["base_url"],
        "pr_num": context["pr_num"],
        "pr_commit": context["pr_commit"],
        "application": app,
        "job_type": job_type,
        "jobs": jobs,
        "job_failures": failures,
    }
    render_application_page(app, job_type, application_context)
    if SAVE_JOB_RESULTS:
        # Store output text files
        for job in jobs:
            store_job_output(job)


def create_application_files(job_type, context):
    if job_type == "run_test":
        jobs = context["tests"]
        job_failures = context["test_failures"]
    else:  # compile type jobs
        jobs = context["builds"]
        job_failures = context["build_failures"]

    # Generate application output files using multiple processes
    with (
        Manager() as manager,
        ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor
    ):
        context_shared = manager.dict(context)
        jobs_shared = manager.dict(jobs)
        job_failures_shared = manager.dict(job_failures)
        for app, app_jobs in jobs_shared.items():
            executor.submit(
                create_application_output,
                app, app_jobs, job_type,
                job_failures_shared[app], context_shared
            )


def get_base_url():
    if LOCAL_TESTING:
        return BASE_URL
    else:
        if PULL_NR is not None and PULL_COMMIT is not None:
            return os.path.join(BASE_URL, PULL_NR, PULL_COMMIT)
        elif BUILD_BRANCH is not None and BUILD_COMMIT is not None:
            return os.path.join(BASE_URL, BUILD_BRANCH, BUILD_COMMIT)
        else:
            return BASE_URL


def static(json_file, output_file):
    base_url = get_base_url()

    with open(output_file) as f:
        main_job_output = f.read()

    # Parse results from json file
    if os.path.exists(json_file):
        with open(json_file) as f:
            results = json.loads(f.read())
        all_jobs = sorted(
            [parse_job(job) for job in results], key=lambda job: job["name"]
        )
    else:
        all_jobs = []

    # Copy favicons to html output directory
    os.makedirs(HTML_DIR, exist_ok=True)
    for status in ["passed", "failed"]:
        shutil.copyfile(
            os.path.join(TEMPLATES_DIR, "{}.png".format(status)),
            os.path.join(HTML_DIR, "{}.png".format(status)),
        )

    # Extract all context data
    context = {
        "base_url": base_url,
        "main_job_output": main_job_output,
        "pr_num": PULL_NR,
        "pr_commit": PULL_COMMIT,
        "build_branch": BUILD_BRANCH,
        "build_commit": BUILD_COMMIT,
    }
    context.update(parse_all_jobs(all_jobs))

    # Render all html files
    render_main_page(context)
    for job_type in ("compile", "run_test"):
        create_application_files(job_type, context)


def dump_to_file(path, data):
    with open(path + ".tmp", "w") as f:
        f.write(data)
    os.rename(path + ".tmp", path)


def post_status(data, prnum, failed_jobs):
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
                failed_job["href"] = os.path.join(get_base_url(), filename)
            status["failed_jobs"].append(failed_job)
    post_data = json.dumps(
        {"cmd" : "prstatus", "prnum" : prnum, "status" : status}
    )
    dump_to_file("prstatus.json", json.dumps(status, indent=True))
    requests.post(MURDOCK_CTRL_URL, data=post_data)


def live(queue, prnum):
    Disque.connect([DISQUE_URL])
    last_update = 0
    failed_jobs = []
    nfailed = 0
    try:
        post_status({"status" : "setting up build" }, prnum, [], "")
        while True:
            _list = Job.wait(queue, count=16)
            for status in _list:
                job = status.get('job')
                if job:
                    job = parse_job(job)
                    filename = store_job_output(job)
                    if job["status"] is False:
                        nfailed += 1
                        if job["name"] == "static_tests":
                            failed_jobs.append((filename, job["name"]))
                        elif nfailed <= MAX_FAILED_DISPLAYED:
                            failed_jobs.append((filename, job["name"]))

                        failed_jobs = failed_jobs[:MAX_FAILED_DISPLAYED]

                        if nfailed > MAX_FAILED_DISPLAYED:
                            failed_jobs.append(
                                (
                                    None,
                                    "({} more failed jobs)"
                                    .format(nfailed - MAX_FAILED_DISPLAYED)
                                )
                            )

                if status.get("status", "") == "done":
                    post_status(None, prnum, failed_jobs)
                    return

                now = time.time()
                if now - last_update > 0.5:
                    post_status(status, prnum, failed_jobs)
                    last_update = now
    except KeyboardInterrupt:
        pass


if __name__=="__main__":
    if len(sys.argv) != 4:
        print(
            "error: {} static <json-data> <output-file> "
            "| live <queue-name> <pr-num>"
            .format(sys.argv[0]),
            file=sys.stderr
        )
        sys.exit(1)

    if sys.argv[1] == "static":
        static(sys.argv[2], sys.argv[3])
    else:
        live(sys.argv[2], sys.argv[3])
