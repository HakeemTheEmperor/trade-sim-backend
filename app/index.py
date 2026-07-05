from app import create_app
app = create_app()

if __name__ == "__main__":
    # Local direct-run only. Never enable debug mode in a deployed environment:
    # Werkzeug's debugger allows arbitrary code execution. Production is served
    # by gunicorn (see bootstrap.sh), not this entry point.
    app.run(debug=False)