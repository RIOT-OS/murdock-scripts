# murdock-scripts
RIOT specific Murdock CI build scripts

See https://github.com/kaspar030/murdock for general information about Murdock.


# DWQ

Start ssh tunnel:

    # ssh -g -f -N riot-labs.de -L7711:localhost:7711

Start a build:

    # time sh riot_build.sh https://github.com/kaspar030/RIOT 6d68a02
