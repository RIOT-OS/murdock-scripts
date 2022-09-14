import json
import os
import sys

def main():
    outdir = os.environ.get("output_dir", os.getcwd())
    infile = os.path.join(outdir, "result.json")

    try:
        with open(infile, "r") as f:
            d = json.load(f)
    except FileNotFoundError:
        print("cannot open %s. exiting." % infile)
        sys.exit(1)

    first_error = True

    for job in d:
        result = job["result"]
        if result["status"] == 0:
            continue

        body = result["body"]

        command = body["command"]
        if not command.startswith("./.murdock error"):
            continue

        if first_error == True:
            print("-- collected errors:")
            first_error = False

        print(result["output"], end="")

if __name__=="__main__":
    main()
