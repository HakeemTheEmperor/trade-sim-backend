# TRADE SIMULATOR API

## OVERVIEW

The Trade Simulator API is a simple application built to simulate stock trading operations. It allows users to interact with a mock trading system backed by a PostgreSQL database, all managed through Docker containers.

## REQUIREMENTS

To run this application, you need to have the following installed on your system:

- Docker: Ensure Docker is installed and running. You can download if from [Docker's official website](https://www.docker.com/get-started/) and follow the installation instructions for your operating system.
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
cd trade-sim-backend
```

2. Build and Run the Application:

   - Use Docker Compose to build and start the application and its PostgreSQL database:

   ```bash
   docker-compose up --build
   ```

   - This command will start the containers and make the API available at http://localhost:5000

3. Shut Down the Application:

   - To stop the containers and remove them, along with the associated volumes (e.g., the PostgreSQL data volume), run:

   ```bash
   docker-compose down -v
   ```

## EMAIL VERIFICATION

Signup emails a 6-digit code and the account stays inactive until it's entered,
so the flow needs an email provider (Brevo). Set these in `.env`:

| Variable | Notes |
|---|---|
| `BREVO_API_KEY` | Brevo v3 API key. **Leave it unset locally** — the code is then written to the server log instead of being emailed, so you can verify accounts without a provider account. |
| `BREVO_SENDER_EMAIL` | required once `BREVO_API_KEY` is set; must be a sender Brevo has verified |
| `BREVO_SENDER_NAME` | optional, defaults to `iMockMarket` |

Full write-up — the OTP parameters, why there's no unverified session, and what
each endpoint deliberately does and doesn't reveal — is in
[docs/email-verification.md](docs/email-verification.md).

## DEVELOPMENT DETAILS

The api was built using Python's Flask framework, by a developer who was just learning flask, so cut me some slack okay. It uses a Postgreql Database running on docker. BYE
