# Use an official Python runtime as the base image
FROM python:3.13-slim

# Set the working directory in the container
WORKDIR /app

# Install system dependencies required for pipenv and PostgreSQL client
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install pipenv
RUN pip install --upgrade pip && pip install pipenv

# Copy the Pipfile and Pipfile.lock to the container
COPY Pipfile Pipfile.lock ./

# Install dependencies using pipenv (gunicorn + Flask-Migrate are now tracked
# in the Pipfile/lock, so --deploy installs everything).
RUN pipenv install --deploy

# Copy the rest of the application code to the container
COPY . .

# Normalize line endings (a CRLF checkout on Windows would make the shebang
# `#!/bin/sh\r`, which fails at runtime) and make the script executable.
RUN sed -i 's/\r$//' ./bootstrap.sh && chmod +x ./bootstrap.sh

# Expose the port Flask runs on
EXPOSE 5000

# Define the command to run your app
CMD ["pipenv", "run", "./bootstrap.sh"]