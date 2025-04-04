# TRADE SIMULATOR API

## OVERVIEW

The Trade Simulator API is a simple application built to simulate stock trading operations. It allows users to interact with a mock trading system backed by a PostgreSQL database, all managed through Docker containers.

## REQUIREMENTS

To run this application, you need to have the following installed on your system:

- Docker: Ensure Docker is installed and running. You can download if from [Docer's official website](https://www.docker.com/get-started/) and follow the installation instructions for your operating system.
- Docker Compose: Docker Compose is typically included with Docker Desktop (for Windows and macOS). If you’re on Linux, you may need to install it separately—[see the Docker Compose installation guide](https://docs.docker.com/compose/install/).

### Optional: Local Development Without Docker

If you prefer to run the application locally without Docker (e.g., for debugging), you’ll need:

- Python 3.13: Download and install python from the [official website](https://www.python.org/downloads/).
- pip: This is included with Python, but you can confirm it is installed by running:

```bash
pip --version
```

- pipenv: Install it with:

```bash
pip install pipenv --user
```

## INSTALLATION

### Using Docker (Recommended)

The application is containerized using Docker, so you don’t need to install Python or dependencies manually on your system. Docker will handle everything for you.

1. Clone the Repository:

```bash
git clone https://github.com/HakeemTheEmperor/trade-sim-backend.git
cd stock-trade-sims
```

2. Build and Run the Application:
   - Use Docker Compose to build and start the application and its PostgreSQL database:
   ```bash
   docker-compose up --build
   ```

To install python, click [here](https://www.python.org/downloads/) and follow the instructions for your operating system

Confirm you have installed python by running:

```bash
python --version
```

Additionally, confirm you have installed pip by running:

```bash
pip --version
```

To install pipenv, run:

```bash
pip install pipenv --user
```

After installing pipenv, run:

```bash
pipenv install
```

to install the packages and dependencies required for the application
Activate the shell by running:

```bash
pipenv shell
```

## DOCKER AND RUN IT

To build the app and run it:

```bash
docker-compose up --build
```

To shut it down and delete the volumes, run:

```bash
docker-compose down -v
```

## DEVELOPMENT DETAILS

The api was built using Python's Flask framework, by a developer who was just learning flask, so cut me some slack okay. It uses a Postgreql Database running on docker. BYE
