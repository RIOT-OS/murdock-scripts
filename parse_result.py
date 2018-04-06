#!/usr/bin/env python3

import io
import json
import sys
import os
import requests
import time

from string import Template
from dwq import Disque, Job

result_dict = {}

sys.stdout = io.TextIOWrapper(sys.stdout.detach(), "utf-8", "replace")

def nicetime(time, tens=True):
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
    if tens:
        res += "%.1fs" % secs
    else:
        res += "%is" % int(secs)
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
def output_name(*args):
    global anchors
    global anchor_num
    name = "output%s" % ("".join(list(args)))
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
    if not job:
        return False
    return job["result"]["status"] in { 0, "0", "pass" }


def create_badge(filename, status="unknown"):
    badge = Template("""
<svg xmlns="http://www.w3.org/2000/svg" width="77" height="20">
<defs>
  <style type="text/css">
    <![CDATA[
      rect {
        fill: #555;
      }
      .passed {
        fill: rgb(68, 204, 17);
      }
      .failed {
        fill: rgb(224, 93, 68);
      }
    ]]>
  </style>
</defs>
<rect rx="3" width="77" height="20" />
<rect rx="3" x="24" width="53" height="20" class="${status}" />
<rect x="24" width="4" height="20" class="${status}" />
<g fill="#fff" text-anchor="middle" font-family="DejaVu Sans,Verdana,Geneva,sans-serif" font-size="11">
  <text x="19" y="14">CI</text>
  <text x="50" y="14">${status}</text>
</g>
</svg>
""")
    with open(filename, "w") as badge_svg:
        badge.substitute(status=status)

def static():
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

    static_tests = result_dict.pop("static_tests", {})
    if nfailed:
        create_badge("badge.svg", "failed")
        print("--- result: BUILD FAILED!")
        if html and ((nfailed > 1) or has_passed(static_tests)):
            print("\n--- ", end="")
            print(html_link("#error0", "JUMP TO FIRST ERROR OUTPUT"))
    else:
        create_badge("badge.svg", "passed")
        print("--- result: BUILD SUCCESSFUL.")

    print("")

    print_static(static_tests)
    print("---")
    print_compiles()
    print("---")
    print_other()
    print("")

    print("--- worker stats:")
    for _worker in sorted(list(workers)):
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
    http_root = os.environ.get("CI_BUILD_HTTP_ROOT", "")
    global result_dict
    d = result_dict.pop("compile", {})

    all_runtime = 0

    all_failed_count = 0
    all_passed_count = 0

    for app in d.values():
        for job in app.values():
            if has_passed(job):
                all_passed_count += 1
            else:
                all_failed_count += 1

    all_count = all_failed_count + all_passed_count

    if not all_count:
        print("--- no compile jobs")
        return

    print("--- compile job results (%s failed, %s passed, %s total):" % \
            (all_failed_count, all_passed_count, all_count))

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

                print(html_link(job_result_link(job, http_root), board),
                        "(%s)" % html_llink(output_name(app, board), "\u2b07"),
                            end="\n" if n==(nfailed -1) else ", ")
                #print(html_link(output_name(app, board), board), end="\n" if n==(nfailed -1) else ", ")
            print("")

        if _passed:
            print("    passed:")
            for n, _tuple in enumerate(_passed):
                app, board, job = _tuple
                print(html_link(job_result_link(job, http_root), board), end="\n" if n==(npassed -1) else ", ")
                #print(html_link(output_name(app, board), board), end="\n" if n==(npassed -1) else ", ")
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
            print("--- build output of app %s for board %s (%s, runtime=%s):" % (app, board, html_link(job_result_link(job, http_root), "raw"), nicetime(job["result"]["runtime"])))
            print(job["result"]["output"], end="")
            print("---")
#    if (all_passed):
#        print("\n--- PASSED build outputs:")
#        for app, board, job in all_passed:
#            html_anchor(output_name(app, board))
#            print("--- build output of app %s for board %s:" % (app, board))
#            print(job["result"]["output"], end="")
#            print("---")

def print_other():
    http_root = os.environ.get("CI_BUILD_HTTP_ROOT", "")
    global result_dict

    for key in result_dict.keys():
        d = result_dict.get(key, {})

        def get_jobs(_dict):
            if "result" in _dict:
                yield _dict
            else:
                for key, val in _dict.items():
                    for job in get_jobs(val):
                        yield job

        jobs = list(get_jobs(d))

        all_failed_count = 0
        all_passed_count = 0

        for job in jobs:
            if has_passed(job):
                all_passed_count += 1
            else:
                all_failed_count += 1

        all_count = all_passed_count + all_failed_count

        print("--- %s job results (%s failed, %s passed, %s total):" % \
                (key, all_failed_count, all_passed_count, (all_failed_count + all_passed_count)))

        failed = []
        passed = []
        total = 0
        _min = -1
        _max = 0
        for job in jobs:
            runtime = job["result"]["runtime"]

            total += runtime
            _min = runtime if _min == -1 else min(runtime, _min)
            _max = max(runtime, _max)
            if has_passed(job):
                passed.append(job)
            else:
                failed.append(job)

        def _print_job(job):
            command = "/".join(job["result"]["body"]["command"].split()[2:])
            job["command"] = command
            print("    " + html_link(job_result_link(job, http_root), command))

        if failed:
            print("    failed:")
            html_anchor("error0")
            for n, job in enumerate(failed):
                _print_job(job)
            print("")

        if passed:
            print("    passed:")
            for n, job in enumerate(passed):
                _print_job(job)
            print("")

        print("\n    runtime: total=%s min=%s max=%s avg=%s" % \
                (nicetime(total), nicetime(_min), nicetime(_max), nicetime(total/(all_count))))

        print("")

        if False:# failed:
            print("--- FAILED %s outputs:" % key)
            for job in failed:
                command = job["command"]
                html_anchor(output_name(command))
                print("--- output of job %s (%s, runtime=%s):" % (command, html_link(job_result_link(job, http_root), "raw"), nicetime(job["result"]["runtime"])))
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

    try:
        merge(result_dict, item)
    except Exception:
        print("error parsing command \"%s\"" % command)

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

def job_result_link(job, httproot, cwd=None):
    filename = job_result_filename(job, cwd)
    if filename:
        return os.path.join(httproot, filename)

def save_job_result(job):
    filename = job_result_filename(job)
    if filename:
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        with open(filename, "w") as f:
            f.write(job["result"]["output"])
        return filename

pbar = Template("""
<div class="col-md-12">
<div class="row">
    <div class="col-md-6">
        <div class="progress">
            <div class="progress-bar progress-bar-striped" role="progressbar" aria-valuenow="${percent}" aria-valuemin="0" aria-valuemax="100" style="width:${percent}%">
                ${percent}%
            </div>
        </div>
    </div>
    <div class="col-md-4">${text}</div>
    <div class="col-md-2">${eta}</div>
</div>
${failed_jobs}
</div>
""")
#<div class="col-md-3"> ETA: ${eta} </div>

def bootstrap_list2grid(_list, gridsize, firstrow):
    res = '<div class="row"><div class="col-md-12">' + firstrow + '</div>'

    for n, field in enumerate(_list):
        if n % gridsize == 0:
            res += '</div><div class="row">'
        res += '<div class="col-md-3">' + field + '</div>'

    for n in range(0, (len(_list) + gridsize) % gridsize):
        res += '<div class="col-md-3"></div>'

    res += '</div>'
    return res

def dump_to_file(path, data):
    with open(path + ".tmp", "w") as f:
        f.write(data)
    os.rename(path + ".tmp", path)

def post_status(data, prnum, failed_jobs, http_root):
    if data:
        total = data.get('total')
        passed = data.get('passed')
        failed = data.get('failed')
        status = data.get('status')
        eta = data.get('eta')

        if (total != None) and (passed != None) and (failed != None):
            done = passed + failed
            percent = str(int((done * 100)/total))
            text = "<span class=\"glyphicon glyphicon-stats\" aria-hidden=\"true\"></span> fail: %s pass: %s done: %s/%s" % (failed, passed, done, total)
            eta = "<span class=\"glyphicon glyphicon-time\" aria-hidden=\"true\"></span> %s" % (nicetime(eta, tens=False))
        else:
            percent = 0
            text="<span class=\"glyphicon glyphicon-transfer\" aria-hidden=\"true\"></span> %s" % status
            eta=""
    else:
        status = None

    failed_jobs_html = ""
    if failed_jobs:
        failed_links = []
        for _tuple in failed_jobs:
            filename, jobname = _tuple
            if filename:
                joblink = "<a href=\"%s\"> %s </a>" % (os.path.join(http_root, filename), jobname)
            else:
                joblink = jobname

            failed_links.append(joblink)

        failed_jobs_html = bootstrap_list2grid(failed_links, 4, "Failed jobs:")

    if status:
        pr_status_html = pbar.substitute(percent=percent, text=text, eta=eta, failed_jobs=failed_jobs_html)
    else:
        if failed_jobs:
            pr_status_html = '<div class="col-md-12">' + failed_jobs_html + '</dev>'
        else:
            pr_status_html = ""

    do_post(pr_status_html, prnum)

def do_post(html, prnum):
    post_data = json.dumps({"cmd" : "prstatus", "prnum" : prnum, "html" : html})

    dump_to_file("prstatus.html.snip", html)

    requests.post('http://localhost:3000/control', data=post_data)

def live():
    global result_dict
    Disque.connect(["localhost:7711"])

    http_root = os.environ.get("CI_BUILD_HTTP_ROOT", "")

    queue = sys.argv[1]
    prnum = sys.argv[2]

    last_update = 0

    maxfailed = 20
    failed_jobs = []
    nfailed = 0

    try:
        post_status({"status" : "setting up build" }, prnum, [], "")
        while True:
            _list = Job.wait(queue, count=16)
            for _status in _list:
                job = _status.get('job')

                if job:
                    filename = save_job_result(job)

                    if filename and not has_passed(job):
                        nfailed += 1
                        jobname = job_name(job)
                        if jobname == "static_tests":
                            failed_jobs = [ (filename, jobname) ] + failed_jobs

                        elif nfailed <= maxfailed:
                            failed_jobs.append((filename, job_name(job)))

                        failed_jobs = failed_jobs[:maxfailed]

                        if nfailed > maxfailed:
                            failed_jobs.append((None, "(%s more failed jobs)" % (nfailed - maxfailed)))

                if _status.get("status", "") == "done":
                    post_status(None, prnum, failed_jobs, http_root)
                    return

                now = time.time()
                if now - last_update > 0.5:
                    post_status(_status, prnum, failed_jobs, http_root)
                    last_update = now


    except KeyboardInterrupt:
        pass

if __name__=="__main__":
    argc = len(sys.argv)
    if argc < 2 or argc > 3:
        printf("error: %s <json-data>|<<queue-name> <pr-num>" % sys.argv[0], file=sys.stderr)
        sys.exit(1)

    if argc == 2:
        static()
    else:
        live()
