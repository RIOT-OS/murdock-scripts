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

TODO
