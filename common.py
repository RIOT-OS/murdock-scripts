"""Common utility functions."""

import os
import re


def nicetime(seconds):
    seconds = abs(int(seconds))
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    if days > 0:
        return f"{days:02d}d {hours:02d}h {minutes:02d}m {seconds:02d}s"
    elif hours > 0:
        return f"{hours:02d}h {minutes:02d}m {seconds:02d}s"
    elif minutes > 0:
        return f"{minutes:02d}m {seconds:02d}s"
    else:
        return f"{seconds:02d}s"


def parse_job(job):
    result = {}
    result["status"] = job["result"]["status"] in { 0, "0", "pass" }
    result["worker"] = job["result"]["worker"]
    result["runtime"] = float(job["result"]["runtime"])
    result["output"] = job["result"]["output"]
    result["name"] = os.path.join(
        *job["result"]["body"]["command"].split()[1:]
    )
    match = re.match(
        r"./.murdock ([a-z_]+) ([a-zA-Z0-9/\-_]+) ([a-zA-Z0-9_\-]+):([a-z]+)",
        job["result"]["body"]["command"]
    )
    if match is not None:
        result["type"] = "tests" if match.group(1) == "run_test" else "builds"
        result["application"] = match.group(2)
        result["target"] = match.group(3)
        result["toolchain"] = match.group(4)
    else:
        result["type"] = result["name"]
    return result
