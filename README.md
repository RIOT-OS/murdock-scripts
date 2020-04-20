# Introduction

This repository contains RIOT specific Murdock build scripts.
It is also the place to collect documentation about RIOT's CI system.

See https://github.com/kaspar030/murdock for general information about Murdock.

# Overview

RIOT's CI is composed of the following tools:

- Murdock as bridge between github and running scripts (https://github.com/kaspar030/murdock)
- dwq for distributing jobs to worker slaves (https://github.com/kaspar030/dwq)
- disque, the backend of dwq (https://github.com/antirez/disque)
- Docker build containers containing RIOT's build environment and a dwq slave (https://github.com/kaspar030/riotdocker branch dwq)
- The scripts in this repository bridging Murdock build jobs and using dwq to build them on worker slaves
- Some HTML files to nicely present Murdock's state (https://github.com/RIOT-OS/murdock-html)
- A Web server proxying HTTPS to Murdock
- SSH for authenticating worker nodes

# Setup of Murdock master node

## disque

Ubuntu has disque packaged. Other distros might need compilation by hand.
Make sure disque is running and listening on 127.0.0.1.

## python modules

    # pip3 install dwq
    # pip3 install agithub
    # pip3 install pytoml

## Murdock

See https://github.com/kaspar030/murdock/blob/master/README.md for generic
Murdock instructions. This guide assumes that there's a murdock user, its home
directory is "/srv/murdock".

Additionally, clone this repository (murdock-scripts) to
"/srv/murdock/murdock-scripts".

Create "/etc/murdock.toml" with the following content (adapt URLs, paths and
credentials):

    data_dir = "/srv/http/ci.riot-labs.de-devel/devel"
    scripts_dir = "/srv/murdock/murdock-scripts"
    http_root = "https://ci.riot-labs.de/devel"
    context = "Murdock2"
    github_username = "kaspar030"
    github_password = "xxx"
    repos = ["RIOT-OS/RIOT"]
    fail_labels = [ "NEEDS SQUASHING", "Waiting For Other PR" ]
    set_status = true

(For testing, better keep "set_status" set to false"...)

Now start "/srv/murdock/murdock/murdock.py /etc/murdock.toml" using your
service supervisor of choice.

## setup dwq authentication

Create a user that'll be used as SSH authentication user.
This user can be restricted to do port forwarding to localhost:7711.
Its .ssh/authorized_keys will contain ssh keys for every allowed worker.

## Setup worker nodes

See https://github.com/kaspar030/riotdocker/blob/dwq/README.md.

## Setup frontend HTTP proxy

nginx example (in addition to SSL setup):

- location / points to the content of https://github.com/RIOT-OS/murdock-html


```
    location /github {

        proxy_set_header        Host $host;
        proxy_set_header        X-Real-IP $remote_addr;
        proxy_set_header        X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header        X-Forwarded-Proto $scheme;

    # Fix the “It appears that your reverse proxy set up is broken" error.
        proxy_pass          http://localhost:3000/github;
        proxy_read_timeout  90;
    }


    location /api {

        proxy_set_header        Host $host;
        proxy_set_header        X-Real-IP $remote_addr;
        proxy_set_header        X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header        X-Forwarded-Proto $scheme;

    # Fix the “It appears that your reverse proxy set up is broken" error.
        proxy_pass          http://localhost:3000/api;
        proxy_read_timeout  90;
    }

    location /status {
        proxy_pass http://localhost:3000/status;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
```


# Cluster management

## Perequisites

Install autossh using package manager, and "dwq" from pip3.


## Setup

1. set up ssh authentication to ci.riot-os.org.

E.g., add this to `~/.ssh/config`:

```
Host murdock
HostName ci.riot-os.org
User murdock-slave
Port 22
IdentityFile ~/.ssh/id_rsa_murdock-slave
IdentitiesOnly yes
LocalForward 7711 127.0.0.1:7711
LocalForward 6379 127.0.0.1:6379
ServerAliveInterval 60
ServerAliveCountMax 2
```

Make sure `~/.ssh/id_rsa_murdock-slave` can log in to `murdock-slave@ci.riot-os.org`.

2. keep an ssh connection open that forwards the ports 7711 and 6379.

E.g., use this alias and "autossh":

    $ alias dwq_connect='autossh -M0 -N -C -f murdock'

Then start up autossh with `dwq_connect` (automate this or repeat for each session).


## dwqm (dwq management utility)

Try "dwqm --help".

Useful things:

- list all queues in the disque instance:

    $ dwqm queue --list

This is a raw queue listing and includes queues used internally by dwq. Those
are named "control::*" and "status::*".

- list all connected workers:

    $ dwqm control --list

- set worker(s) to "paused", will not run any jubs until resumed or restarted:

    $ dwqm control --pause  worker1 [worker2] ...

- resume worker(s):

    $ dwqm control --resume  worker1 [worker2] ...

- shutdown worker(s) (with our current murdock scripts, this will shutdown the
  worker, pull the newest build container, then __restart__ the worker):

    $ dwqm control --shutdown  worker1 [worker2] ...

## dwqc (dwq client, runs jobs on queue)

In our setup, every build worker listens on the "default" queue. Those workers
are executing inside of the build container.

Every test worker listens on a queue named after the board it is connected to,
e.g., "samr21-xpro", "nrf52dk" or "esp32-wroom-32".

__every__ worker also listens on a queue named after it's hostname

For example, in our setup, "riotbuild" listens on the queues "default" and
"riotbuild", "pi-36f90aef" listend on "pi-36f90aef" and "nrf52dk".

`dwqc` needs a git repo and commit either as parameters or via environment.
Either manually set "DWQ_REPO" and "DWQ_COMMIT", or use an alias:

    $ alias dwqset='export DWQ_REPO=https://github.com/RIOT-OS/RIOT DWQ_COMMIT=$(git rev-parse HEAD)'
    $ cd src/riot
    $ dwqset    # following dwqc jobs will now be executed in the specified checkout


Run a single job on the queue named "default":

    $ dwqc "echo hello world!"

Run a single job on a specific queue:

    $ dwqc -q riotbuild "ccache -s"

Run multiple jobs on a single queue:

    $ for i in $(seq 10); do echo "echo $i"; done | dwqc -q queue_name

Create command from stdin plus base command:

    $ echo "first second third" | dwqc -s "echo \${1}" # will create job "echo first"
