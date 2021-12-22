""" Application factory """

import os
from tempfile import mkdtemp
from flask import Flask, redirect, url_for
from flask_session import Session


def create_app():
    """
    Create Flask application, configure it with MOEX_SANDBOX_SETTINGS environment variable.
    :return: Flask app.
    """

    app = Flask(__name__, instance_relative_config=True)

    app.config.from_mapping(
        # Default settings
        TESTING=False,
        # Configure session to use filesystem (with random directory for every session cookie instead of signed cookies)
        SESSION_FILE_DIR=app.instance_path + mkdtemp(),
        SESSION_PERMANENT=False,
        SESSION_TYPE="filesystem",
        # Ensure templates are auto-reloaded
        TEMPLATES_AUTO_RELOAD=True
    )

    # Override it with ENV
    app.config.from_envvar('MOEX_SANDBOX_SETTINGS')

    '''
    # Ensure responses aren't cached
    @app.after_request
    def after_request(response):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Expires"] = 0
        response.headers["Pragma"] = "no-cache"
        return response
    '''
    # Configure session to use filesystem (instead of signed cookies)
    Session(app)

    # Create instance directory
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    # Create tmp directory in root folder to store client session cookies
    try:
        os.makedirs(app.instance_path + '/tmp')
    except OSError:
        pass

    # Create jinja filter to format html output
    def finance(value):
        """Format value as finance."""
        return f"{value:,.2f}"

    app.jinja_env.filters["finance"] = finance

    # Register helpers_functions interface class
    from . import helpers
    helpers.helpers_functions.database_name = app.config.get("DATABASE")

    # Create database if it is not exist
    from . import db
    if not os.path.isfile(app.config.get("DATABASE")):
        with app.app_context():
            db.init_db()

    # Register app with db.py (database logic)
    db.init_app(app)

    # Register scheduler.py (schedule functions)
    from . import schedule
    schedule.init(app.config.get("DATABASE"))

    # Register auth blueprint
    from . import auth
    app.register_blueprint(auth.bp)

    # Register sandbox blueprint
    from . import sandbox
    app.register_blueprint(sandbox.bp)

    '''
    # Create test view
    @app.route("/hello")
    def hello():
        return "Hello from Flask app"
    '''

    @app.route("/")
    def index():
        return redirect('/sandbox/depo')

    return app
