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

# Install dependencies using pipenv
RUN pipenv install --deploy

# Install the production WSGI server into the pipenv virtualenv. Pinned for
# reproducibility; kept out of the Pipfile so the full lockfile isn't re-resolved.
RUN pipenv run pip install "gunicorn==23.0.0"

# Copy the rest of the application code to the container
COPY . .

# Make the bootstrap.sh script executable
RUN chmod +x ./bootstrap.sh

# Expose the port Flask runs on
EXPOSE 5000

# Define the command to run your app
CMD ["pipenv", "run", "./bootstrap.sh"]