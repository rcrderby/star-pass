# star-pass Container
#
# One file and two targets, so the image the scheduled Slack summary
# runs from and the image the deployment runs cannot drift apart on
# the base image, the Python version or the system packages:
#
#   docker build --target slack -t star-pass:slack .
#   docker build -t star-pass .
#
# The full target is last on purpose.  A build naming no target gets
# the last stage, which is what 'compose.yaml' and the build workflow
# ask for, so neither has to know this file has more than one.

# What both targets are built on: the interpreter, the system packages
# and the import root.  No application dependency is installed here,
# because which ones are installed is the whole difference between
# them.
FROM python:3.12-slim AS base

# Set the working directory
WORKDIR /app

# Update OS package list, install packages, and clear apt cache
RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy the Python pip requirements files.  Both files reach both
# targets because the runtime file reads the core one, so a target
# given only the file it installs from could not install from it.
COPY requirements/requirements_core.txt requirements/requirements_core.txt
COPY requirements/requirements.txt requirements/requirements.txt

# Upgrade pip once, above both targets
RUN python -m pip install --no-cache-dir --upgrade pip

# Set the PYTHONPATH environment variable
ENV PYTHONPATH=/app

# The image the scheduled Slack sign-up summary runs from, and the way
# to run that summary by hand without bringing a deployment up.
#
# It installs the core requirements alone, which is everything
# '__main__.py -s' imports and nothing else: no 'fastapi', 'uvicorn',
# 'httpx2' or 'jsonschema'.  The code is not changed to achieve that
# and must not be -- the entry point keeps importing 'star_pass_cli'
# and the contract exactly as it does now, because one dispatcher for
# both ways in is worth more than the megabytes a lazy import would
# save.
#
# What it does not carry: 'web/', because it serves nothing, and
# '/data', because the '-s' path opens no database and the runner it
# runs on is destroyed after every post.
FROM base AS slack

# Install the requirements every way in needs
RUN python -m pip install --no-cache-dir -r requirements/requirements_core.txt && \
    rm -rf requirements

# Copy the /app directory to the image
COPY /app /app

# Copy the shift data model, which 'star_pass._defaults' reads at import
# time from a path relative to the package ('<app>/../models').
COPY /models /models

# A run that is given no command builds the message and posts nothing:
# check mode is the default, and the summary is the only thing this
# image is for.  The scheduled workflow names the command in full
# anyway, because the window it covers is an argument.
CMD ["python", "/app/__main__.py", "-s"]

# Everything star-pass does: the API service, the frontend and the
# command line, which ship together so that the core and the service
# cannot drift (D17).
FROM base AS full

# Install the requirements from the requirements file, which reads the
# core file first
RUN python -m pip install --no-cache-dir -r requirements/requirements.txt && \
    rm -rf requirements

# Copy the /app directory to the image
COPY /app /app

# Copy the shift data model, which 'star_pass._defaults' reads at import
# time from a path relative to the package ('<app>/../models').
COPY /models /models

# Copy the page the front-end service serves at its root, which it
# reads from the same kind of path ('<app>/../web').  It ships in the
# image because it can only work from that service's origin: the token
# a write carries is a cookie the page reads, and a write from another
# origin is refused (D4, D18).
COPY /web /web

# Create the directory the SQLite database lives in, so a deployment
# can mount a volume over it.
RUN mkdir -p /data

# Start the bash prompt
CMD ["/bin/bash"]
