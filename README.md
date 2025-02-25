# TRADE SIMULATOR API

## REQUIREMENTS

To run our application, you need to have python (at least python3) installed as well as pipenv.

## INSTALLATION

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

## DOCKER

To build the postgresql database, run:

```bash
docker-compose up -d
```

And to shut it down, run:

```bash
docker-compose down -v
```

## RUN THE APP

To run the app, run:

```bash
./bootstrap.sh
```

## DEVELOPMENT DETAILS

The api was built using Python's Flask framework, by a developer who was just learning flask, so cut me some slack okay. It uses a Postgreql Database running on docker. BYE
