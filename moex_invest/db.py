"""
Database logic.
db.py registered at __init__.py and app init with init_app()
"""

import sqlite3
from flask import current_app, g
from moex_invest.helpers import helpers_functions



def init_app(app):
    """
    Register close_db() function with app instance (app get from __init__.py create_app() function)
    :param app: flask application
    :return: None
    """

    # Call it after every request (if forgot close db manually)
    app.teardown_appcontext(close_db)


def get_db():
    """
    Return database connection with row factory as sqlite3.Row
    :return: sqlite3.connection
    """

    if 'db' not in g:
        db_name = current_app.config.get("DATABASE")

        if not db_name:
            helpers_functions.app_log_add(f"Error. db.py get_db(): your application has not database.")
            raise ValueError

        g.db = sqlite3.connect(current_app.config.get("DATABASE"), detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row

    return g.db


# e get with teardown_appcontext method (look at init_app function here)
def close_db(e=None):
    """
    Close db connection if it is existed
    :return: None
    """
    db = g.pop('db', None)
    if db:
        db.close()


def init_db():
    """
    Initialize database from schema.sql
    : db - sqlite3 connection to app.config.get('DATABASE')
    :return: None
    """
    db = get_db()

    with current_app.open_resource('schema.sql') as f:
        db.executescript(f.read().decode('utf8'))

    # Add tickers to database listing table

    helpers_functions.app_log_add(f"Success. db.py init_db(): Create database {current_app.config.get('DATABASE')}. "
                f"Length of tickers from moex to listing table in database is "
                f"{helpers_functions.take_symbols()}")





