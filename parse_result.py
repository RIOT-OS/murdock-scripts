#!/usr/bin/env python3

import json
import sys

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

def main():
    passed = {}
    failed = {}
    _time = {}
    workers = set()
    with open(listget(sys.argv, 1, "result.json"), "r") as f:
        results = json.load(f)
        for job in results:
            result = job["result"]

            worker = result["worker"]
            workers.add(worker)

            _failed = not (result["status"] in { 0, "0", "pass" })
            if _failed:
                dictadd(failed, worker)
            else:
                dictadd(passed, worker)

            dictadd(_time, worker, result.get("runtime"))

            if _failed:
                print(" -- worker %s ---" % worker)
                print(result["output"])
                print(" -- ")

    print("--- stats:")
    for _worker in workers:
        _pass = passed.get(_worker) or 0
        fail = failed.get(_worker) or 0
        total = _pass + fail
        print(_worker, "total:", total, "pass:", _pass, "fail:", fail, \
                "avg: %.1fs" % ( _time.get(_worker) / total))

if __name__=="__main__":
    main()
