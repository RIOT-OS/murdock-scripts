#!/usr/bin/env python3

import json
import sys
import os

result_dict = {}

def nicetime(time):
    secs = round(time, ndigits=1)
    minutes = secs/60
    hrs = int(minutes/60)
    days = int(hrs/24)
    secs = float(secs % 60)
    minutes = int(minutes % 60)
    hrs = int(hrs % 24)
    res = ""
    if days:
        res += "%id:" % days
    if hrs:
        res += "%ih:" % hrs
    if minutes:
        if hrs and minutes < 10:
            res += "0"
        res += "%im:" % minutes
    if minutes and secs < 10:
            res += "0"
    res += "%.1fs" % secs
    return res

html = (os.environ.get("HTML") or "false").lower() in { "true", "1" }

def html_link(target, text=""):
    if not html:
        return text
    return "<A HREF=\"%s\">%s</A>" % (target, text)

def html_llink(target, text=""):
    return html_link("#%s" % target, text)

def html_anchor(name, text=""):
    if not html:
        print(text, end="")
    else:
        print("<A NAME=\"%s\">%s</A>" % (name, text), end="")

anchors = {}
anchor_num = 0
def output_name(app, board):
    global anchors
    global anchor_num
    name = "output%s%s" % (app, board)
    anchor = anchors.get(name)
    if not anchor:
        anchor = "a%i" % anchor_num
        anchors[name] = anchor
        anchor_num += 1
    return anchor

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

def dictadd(_dict, key, val=1, ret_post=True):
    pre = _dict.get(key)
    post = (pre or 0) + val
    _dict[key] = post
    if ret_post:
        return post
    else:
        return pre

def listget(_list, n, default=None):
    try:
        return  _list[n]
    except IndexError:
        return default

def has_passed(job):
    return job["result"]["status"] in { 0, "0", "pass" }

def main():
    passed = {}
    failed = {}
    npassed = 0
    nfailed = 0
    _time = {}
    workers = set()
    with open(listget(sys.argv, 1, "result.json"), "r") as f:
        results = json.load(f)
        for job in results:
            result = job["result"]

            worker = result["worker"]
            workers.add(worker)

            if has_passed(job):
                npassed += 1
                dictadd(passed, worker)
            else:
                nfailed += 1
                dictadd(failed, worker)

            dictadd(_time, worker, result.get("runtime"))

            process(job)

    static_tests = result_dict.get("static_tests")
    if nfailed:
        print("--- result: BUILD FAILED!")
        if html and ((nfailed > 1) or has_passed(static_tests)):
            print("\n--- ", end="")
            print(html_link("#error0", "JUMP TO FIRST ERROR OUTPUT"))
    else:
        print("--- result: BUILD SUCCESSFUL.")

    print("")

    print_static(static_tests)
    print("---")
    print_compiles()
    print("")

    print("--- worker stats:")
    for _worker in workers:
        _pass = passed.get(_worker) or 0
        fail = failed.get(_worker) or 0
        total = _pass + fail
        print(_worker, "total:", total, "pass:", _pass, "fail:", fail, \
                "avg: %.1fs" % ( _time.get(_worker) / total))

def print_static(job):
    if not job:
        return

    print("--- static tests:", "passed" if has_passed(job) else "failed!")
    print(job["result"]["output"])

def print_compiles():
    global result_dict
    d = result_dict["compile"]

    print("--- compile job results:")

    all_runtime = 0
    all_count = 0

    all_failed = []
    all_passed = []
    for app in sorted(d.keys()):
        boards = sorted(d[app].keys())

        last = len(boards)-1
        _failed = []
        _passed = []
        total = 0
        _min = -1
        _max = 0
        for n, board in enumerate(boards):
            all_count += 1
            job = d[app][board]
            runtime = job["result"]["runtime"]

            all_runtime += runtime
            total += runtime
            _min = runtime if _min == -1 else min(runtime, _min)
            _max = max(runtime, _max)
            if has_passed(job):
                _passed.append((app, board, job))
            else:
                _failed.append((app, board, job))

        npassed = len(_passed)
        nfailed = len(_failed)
        ntotal = npassed + nfailed
        print("%s (%s/%s):\n" % (app, npassed, ntotal))

        if _failed:
            print("    failed:")
            for n, _tuple in enumerate(_failed):
                app, board, job = _tuple

                print(html_llink(output_name(app, board), board), end="\n" if n==(nfailed -1) else ", ")
            print("")

        if _passed:
            print("    passed:")
            for n, _tuple in enumerate(_passed):
                app, board, job = _tuple
                print(html_llink(output_name(app, board), board), end="\n" if n==(npassed -1) else ", ")
            print("")

        print("\n    runtime: total=%s min=%s max=%s avg=%s" % \
                (nicetime(total), nicetime(_min), nicetime(_max), nicetime(total/(npassed + nfailed))))

        print("")

        all_failed.extend(_failed)
        all_passed.extend(_passed)

    print("\n    total cpu runtime:", nicetime(all_runtime))

    if (all_failed):
        print("")
        html_anchor("error0")
        print("--- FAILED build outputs:")
        for app, board, job in all_failed:
            html_anchor(output_name(app, board))
            print("--- build output of app %s for board %s:" % (app, board))
            print(job["result"]["output"], end="")
            print("---")
    if (all_passed):
        print("\n--- PASSED build outputs:")
        for app, board, job in all_passed:
            html_anchor(output_name(app, board))
            print("--- build output of app %s for board %s:" % (app, board))
            print(job["result"]["output"], end="")
            print("---")

def process(job):
    global result_dict
    command = reversed(job["result"]["body"]["command"].split()[1:])

    item = job
    last = {}
    for part in command:
        last[part] = item
        item = last
        last = {}

    merge(result_dict, item)

if __name__=="__main__":
    main()
