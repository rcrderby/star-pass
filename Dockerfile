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
# Pinned by digest rather than by tag.  '3.12-slim' moves, so two
# builds of one commit could differ in their base layer, which is
# what a pinned requirements file exists to prevent one level up.
# Dependabot's docker ecosystem raises this the way it raises a
# pinned package.
FROM python:3.14-slim@sha256:cae66f2ef0ec51a9891263eeee7f987dacf0a9879e8aa9353d5606e0530619a5 AS base

# Set the working directory
WORKDIR /app

# Copy the Python pip requirements files.  All three reach both
# targets because the runtime file reads the other two, so a target
# given only the file it installs from could not install from it.
COPY requirements/requirements_core.txt requirements/requirements_core.txt
COPY requirements/requirements_service.txt \
     requirements/requirements_service.txt
COPY requirements/requirements.txt requirements/requirements.txt

# Upgrade pip once, above both targets
RUN python -m pip install --no-cache-dir --upgrade pip

# Set the PYTHONPATH environment variable
ENV PYTHONPATH=/app

# The account both targets run as.  Created here so that neither
# target can be the one that forgets, and given a fixed UID and GID
# rather than allocated ones, because '/data' is a named volume:
# Docker copies the image directory's ownership into an empty volume
# the first time it is mounted, so the number in the image is the
# number that ends up on the volume, and a number that moved between
# builds would leave an existing volume unreadable.
#
# 'USER' is set at the end of each target instead of here.  The
# installs below it run as root because that is what writing to
# site-packages needs, and a stage that ends as root is the thing
# hadolint's DL3002 is for.
RUN groupadd --gid 1000 starpass && \
    useradd --uid 1000 --gid 1000 --no-log-init --create-home starpass

# The image the scheduled Slack sign-up summary runs from, and the way
# to run that summary by hand without bringing a deployment up.
#
# It installs the core requirements alone, which is everything
# '__main__.py -s' imports and nothing else: no 'fastapi', 'uvicorn'
# or 'httpx2'.  The code is not changed to achieve that
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

# Make the copied tree readable by anything that is not root.  'COPY'
# carries the build context's own modes into the image, so a checkout
# whose directories are 0700 -- which is what a working tree inside a
# synchronised folder can be -- produces an image the account below
# cannot read, while a fresh clone in continuous integration produces
# one it can.  Stating the mode here removes the difference.
#
# 'a+rX' adds execute to directories and to what already had it, so
# '__main__.py' keeps its own bit and no module is made executable.
RUN chmod -R a+rX /app /models

# Nothing here is written to: the summary reads the data model, asks
# Amplify and posts to Slack.  What the account buys is that the
# scheduled run holds no more privilege than the post needs.
USER starpass

# A run that is given no command builds the message and posts nothing:
# check mode is the default, and the summary is the only thing this
# image is for.  The scheduled workflow names the command in full
# anyway, because the window it covers is an argument.
CMD ["python", "/app/__main__.py", "-s"]

# Everything star-pass does: the API service, the frontend and the
# command line, which ship together so that the core and the service
# cannot drift.
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
# origin is refused.
COPY /web /web

# Create the directory the SQLite database lives in, so a deployment
# can mount a volume over it, and give it to the account that writes
# the database.
#
# The ownership is what makes the mount work.  Docker copies an empty
# named volume's ownership and mode from the directory it is mounted
# over, so a volume created against this image belongs to 'starpass'
# from the moment it exists.  It copies nothing onto a volume that
# already has content, which is why this change belongs to a phase
# where the volume is empty: an existing volume stays root-owned and
# has to be chowned by hand or discarded.
#
# SQLite writes '-wal' and '-shm' beside the database, so the
# directory has to be writable and not merely the file.
#
# The 'chmod' is here for the reason the Slack target states: 'COPY'
# carries the build context's directory modes into the image, and a
# 0700 directory in the checkout is a tree the account cannot read.
RUN chmod -R a+rX /app /models /web && \
    mkdir -p /data && \
    chown starpass:starpass /data

# Everything else in the image stays root-owned and is only read:
# '/app', '/models' and '/web' are the code, the data model and the
# page, and a process that cannot rewrite them is one fewer way for a
# write to become a deployment.
USER starpass

# What the image does when nobody says. The compose file names a
# command for each service it runs, so this is only reached by
# somebody running the image by hand -- and for them the command line's
# own help is a better answer than a shell prompt, which looks like a
# container that started and did nothing.
CMD ["python", "/app/__main__.py", "--help"]
