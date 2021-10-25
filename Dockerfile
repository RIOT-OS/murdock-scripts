FROM riot/murdock:latest

LABEL maintainer="alexandre.abadie@inria.fr"

# Install tools required by the murdock scripts
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        bsdmainutils \
        git \
        && \
    apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

RUN python3 -m pip install --upgrade pip && \
    python3 -m pip install \
        dwq==0.0.47 \
        jinja2==3.0.2 \
        minify_html==0.6.10
