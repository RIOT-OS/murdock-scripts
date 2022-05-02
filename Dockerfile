FROM ubuntu:jammy

LABEL maintainer="alexandre.abadie@inria.fr"

# Install tools required by the murdock scripts
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        bsdmainutils \
        git \
        python3-pip \
        ssh-client \
        wget \
        && \
    apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

RUN python3 -m pip install --upgrade pip && \
    python3 -m pip install \
        dwq==0.0.52 \
        orjson==3.6.6

# get git-cache directly from github
RUN wget https://raw.githubusercontent.com/kaspar030/git-cache/f76c3a5f0e15f08c28e53fb037755f29f0b76d88/git-cache \
        -O /usr/bin/git-cache \
        && chmod a+x /usr/bin/git-cache

# Set a global system-wide git user and email address
RUN git config --system user.name "riot" && \
    git config --system user.email "riot@riot-labs.de"

RUN mkdir -p /opt/murdock-scripts
COPY . /opt/murdock-scripts

RUN chmod +x /opt/murdock-scripts/build.sh
RUN chmod +x /opt/murdock-scripts/reporter.py
RUN chmod +x /opt/murdock-scripts/process_result.py

CMD ["/opt/murdock-scripts/build.sh"]
