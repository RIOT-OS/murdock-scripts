#!/usr/bin/env python3

import copy
import json
import os

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

def merge_add(a, b, path=None):
    "merges b into a"
    if path is None: path = []
    for key in b:
        if key in a:
            if isinstance(a[key], dict) and isinstance(b[key], dict):
                merge_add(a[key], b[key], path + [str(key)])
            else:
                a[key] += b[key]

        else:
            a[key] = b[key]

    return a

def extract_buildsizes(output):
    lines = iter(output.split("\n"))
    for line in lines:
        if line == "   text\t   data\t    bss\t    dec\t    hex\tfilename":
            fields = line.split('\t')
            vals = next(lines).split('\t')
            result = {}
            for n, field in enumerate(fields):
                field = field.lstrip().rstrip()
                if field in { "hex", "filename" }:
                    continue
                result[field] = int(vals[n].lstrip().rstrip())

            return result

def main():
    outdir = os.environ.get("output_dir", os.getcwd())
    infile = os.path.join(outdir, "result.json")
    outfile = os.path.join(outdir, "sizes.json")

    with open(infile, "r") as f:
        d = json.load(f)

    buildsizes = {}
    app_totals = {}
    board_totals = {}

    for job in d:
        result = job["result"]
        if result["status"] != 0:
            continue

        body = result["body"]

        command = body["command"]
        if not command.startswith("./.murdock compile"):
            continue

        sizes = extract_buildsizes(result["output"])
        if sizes:
            _command = command.split(" ")
            app = _command[2]
            board = _command[3]
            merge(buildsizes, { app : { board : copy.deepcopy(sizes) } })

            sizes["count"] = 1

            merge_add(app_totals, { app : copy.deepcopy(sizes) })
            merge_add(board_totals, { board : copy.deepcopy(sizes) })

    result = { "sizes" : buildsizes, "app_totals" : app_totals, "board_totals" : board_totals }
    with open(outfile, "w") as f:
        json.dump(result, f, sort_keys=True, indent=4)

if __name__=="__main__":
    main()
