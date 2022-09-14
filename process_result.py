#!/usr/bin/env python3

import os
import statistics
import sys

import orjson

from common import parse_job, nicetime


RESULT_JSON_FILE = "result.json"


def parse_result(jobs):
    jobs = sorted(
        [parse_job(job) for job in jobs], key=lambda job: job["name"]
    )
    builds = {
        job["application"]: [] for job in jobs if job["type"] == "builds"
    }
    build_success = {
        application: [] for application in builds
    }
    build_failures = {
        application: [] for application in builds
    }
    tests = {
        job["application"]: [] for job in jobs if job["type"] == "tests"
    }
    test_success = {
        application: [] for application in tests
    }
    test_failures = {
        application: [] for application in tests
    }
    workers_runtimes = {}
    workers_failed = {}
    workers_passed = {}
    builds_count = 0
    build_success_count = 0
    build_failures_count = 0
    tests_count = 0
    test_success_count = 0
    test_failures_count = 0
    for job in jobs:
        if "application" not in job:
            continue
        job.pop("output")
        application = job["application"]
        worker = job["worker"]
        if worker not in workers_failed:
            workers_failed.update({worker: 0})
        if worker not in workers_passed:
            workers_passed.update({worker: 0})
        if job["type"] == "builds":
            builds_count += 1
            builds[application].append(job)
            if worker not in workers_runtimes:
                workers_runtimes.update({worker: []})
            workers_runtimes[worker].append(job["runtime"])
            if job["status"] is False:
                build_failures_count += 1
                build_failures[application].append(job)
                workers_failed[worker] += 1
            else:
                build_success_count += 1
                build_success[application].append(job)
                workers_passed[worker] += 1
            continue
        if job["type"] == "tests":
            tests_count += 1
            tests[application].append(job)
            if worker not in workers_runtimes:
                workers_runtimes.update({worker: []})
            workers_runtimes[worker].append(job["runtime"])
            if job["status"] is False:
                test_failures_count += 1
                test_failures[application].append(job)
                workers_failed[worker] += 1
            else:
                test_success_count += 1
                test_success[application].append(job)
                workers_passed[worker] += 1

    total_build_time = nicetime(sum([
        sum(runtimes) for _, runtimes in workers_runtimes.items()
    ]))

    return {
        "jobs_count": builds_count + tests_count,
        "builds": builds,
        "builds_count": builds_count,
        "build_success": build_success,
        "build_success_count": build_success_count,
        "build_failures": build_failures,
        "build_failures_count": build_failures_count,
        "tests": tests,
        "tests_count": tests_count,
        "test_success": test_success,
        "test_failures": test_failures,
        "test_success_count": test_success_count,
        "test_failures_count": test_failures_count,
        "workers": sorted(workers_runtimes.keys()),
        "worker_runtimes": workers_runtimes,
        "workers_failed": workers_failed,
        "workers_passed": workers_passed,
        "total_time": total_build_time,
    }


def create_application_files(job_type, all_results):
    if job_type == "tests":
        jobs = all_results["tests"]
        jobs_failure = all_results["test_failures"]
    else:  # builds type jobs
        jobs = all_results["builds"]
        jobs_failure = all_results["build_failures"]

    for application, app_jobs in jobs.items():
        # Store output text files
        output_path = os.path.join("output", job_type, application)
        os.makedirs(output_path, exist_ok=True)
        app_data = {
            "jobs": app_jobs,
            "failures": jobs_failure[application],
        }
        app_data_filename = os.path.join(output_path, "app.json")
        with open(app_data_filename, "w") as app_json:
            app_json.write(orjson.dumps(app_data).decode())


def main():
    if not os.path.exists(RESULT_JSON_FILE):
        print(f"No {RESULT_JSON_FILE} file found, aborting")
        sys.exit(1)

    with open(RESULT_JSON_FILE) as f:
        results = orjson.loads(f.read())

    # Extract and reformat all result data
    results_parsed = parse_result(results)

    builds = []
    for build in results_parsed["builds"].keys():
        builds.append(
            {
                "application": build,
                "build_count": len(results_parsed["builds"][build]),
                "build_success": len(results_parsed["build_success"][build]),
                "build_failures": len(results_parsed["build_failures"][build]),
            }
        )

    with open("builds.json", "w") as build_json:
        build_json.write(orjson.dumps(builds).decode())

    build_failures = []
    for build, failures in results_parsed["build_failures"].items():
        for job in failures:
            build_failures.append(
                {
                    "application": build,
                    "target": job["target"],
                    "toolchain": job["toolchain"],
                    "worker": job["worker"],
                    "runtime": job["runtime"],
                }
            )

    with open("build_failures.json", "w") as build_failures_json:
        build_failures_json.write(
            orjson.dumps(build_failures).decode()
        )

    tests = []
    for test in results_parsed["tests"].keys():
        tests.append(
            {
                "application": test,
                "failures": results_parsed["test_failures"][test],
                "test_count": len(results_parsed["tests"][test]),
                "test_success": len(results_parsed["test_success"][test]),
                "test_failures": len(results_parsed["test_failures"][test]),
            }
        )

    with open("tests.json", "w") as test_json:
        test_json.write(orjson.dumps(tests).decode())

    test_failures = []
    for test, failures in results_parsed["test_failures"].items():
        for job in failures:
            test_failures.append(
                {
                    "application": test,
                    "target": job["target"],
                    "toolchain": job["toolchain"],
                    "worker": job["worker"],
                    "runtime": job["runtime"],
                }
            )

    with open("test_failures.json", "w") as test_failures_json:
        test_failures_json.write(
            orjson.dumps(test_failures).decode()
        )

    stats = {
        "total_jobs": results_parsed["jobs_count"],
        "total_builds": results_parsed["builds_count"],
        "total_tests": results_parsed["tests_count"],
        "total_time": results_parsed["total_time"],
        "workers": [
            {
                "name": worker,
                "runtime_avg": statistics.mean(
                    results_parsed["worker_runtimes"][worker]
                ),
                "runtime_min": min(results_parsed["worker_runtimes"][worker]),
                "runtime_max": max(results_parsed["worker_runtimes"][worker]),
                "total_cpu_time": sum(
                    results_parsed["worker_runtimes"][worker]
                ),
                "jobs_failed": results_parsed["workers_failed"][worker],
                "jobs_passed": results_parsed["workers_passed"][worker],
                "jobs_count": len(results_parsed["worker_runtimes"][worker]),
            }
            for worker in results_parsed["workers"]
        ]
    }

    with open("stats.json", "w") as stats_json:
        stats_json.write(orjson.dumps(stats).decode())

    for job_type in ("builds", "tests"):
        create_application_files(job_type, results_parsed)


if __name__=="__main__":
    main()
