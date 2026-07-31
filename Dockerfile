# star-pass Container
FROM python:3.12-slim

# Set the working directory
WORKDIR /app

# Update OS package list, install packages, and clear apt cache
RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy the Python pip requirements file
COPY requirements/requirements.txt requirements/requirements.txt

# Upgrade pip and install requirements from the requirements file
RUN python -m pip install --no-cache-dir --upgrade pip && \
    python -m pip install --no-cache-dir -r requirements/requirements.txt && \
    rm -rf requirements

# Set the PYTHONPATH environment variable
ENV PYTHONPATH=/app

# Copy the /app directory to the image
COPY /app /app

# Copy the shift data model, which 'star_pass._defaults' reads at import
# time from a path relative to the package ('<app>/../models').
COPY /models /models

# Create the CSV input and JSON output directories that the Google
# Calendar and Amplify shift run modes read from and write to.
RUN mkdir -p /data/csv /data/json

# Start the bash prompt
CMD ["/bin/bash"]
