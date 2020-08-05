#!/usr/bin/env python3

import copy
import json
import os
import sys

def merge(a, b, path=None):
    "merges b into a"
    if path is None: path = []
    for key in b:
        if key in a:
            if isinstance(a[key], dict) and isinstance(b[key], dict):
                merge(a[key], b[key], path + [str(key)])
            elif a[key] == b[key]:
                pass # same leaf value
            else:
                raise Exception('Conflict at %s' % '.'.join(path + [str(key)]))
        else:
            a[key] = b[key]
    return a


def extract_json_metrics(output):
    metrics = {}
    lines = iter(output.split("\n"))
    for line in lines:
        if line.startswith("{"):
            try:
                metric = json.loads(line)
                print(metrics, metric)
                metrics = merge(metrics, metric)
            except json.decoder.JSONDecodeError:
                pass

    return metrics


def main():
    outdir = os.environ.get("output_dir", os.getcwd())
    infile = os.path.join(outdir, "result.json")
    outfile = os.path.join(outdir, "metrics.json")

    try:
        with open(infile, "r") as f:
            d = json.load(f)
    except FileNotFoundError:
        print("cannot open %s. exiting." % infile)
        sys.exit(1)

    merged_metrics = {}

    for job in d:
        result = job["result"]
        if result["status"] != 0:
            continue

        body = result["body"]

        command = body["command"]
        if not (command.startswith("./.murdock compile") or
               command.startswith("./.murdock run_test")):
            continue

        metrics = extract_json_metrics(result["output"])
        if metrics:
            _command = command.split(" ")
            app = _command[2]
            board = _command[3]
            merge(merged_metrics, { app : { board : copy.deepcopy(metrics) } })

    result = { "metrics" : merged_metrics }
    with open(outfile, "w") as f:
        json.dump(result, f, sort_keys=True, indent=4)

if __name__=="__main__":
    main()
