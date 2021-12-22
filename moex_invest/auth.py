"""
Authentication blueprint
"""

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for
from functools import wraps
from werkzeug.security import check_password_hash, generate_password_hash
from moex_invest.db import get_db
from moex_invest.helpers import helpers_functions
import re

bp = Blueprint('auth', __name__, url_prefix="/auth")


@bp.route("/register", methods=("GET", "POST"))
def register():
    """Register user"""
    # POST request from client
    if request.method == "POST":
        # Get input from client
        username = str(request.form.get("username"))
        password = str(request.form.get("password"))
        conformation = request.form.get("confirmation")
        email = request.form.get("email")
        acc_type = request.form.get("type")

        # Check username and password
        if not username or len(username) > 20:
            flash(f"Извините, похоже что-то не так с вашим username. ({username})")
            return redirect("/auth/register")
        if not password or len(password) > 20:
            flash(f"Извините, похоже что-то не так с вашим password. ({password})")
            return redirect("/auth/register")
        if not conformation or len(conformation) > 20:
            flash(f"Извините, похоже что-то не так с вашим подтверждением пароля. Попробуйте ввести confirm password "
                  f"еще раз.")
            return redirect("/auth/register")
        if password != conformation:
            flash(f"Извините, похоже пароль и подтверждение не одинаковы.")
            return redirect("/auth/register")
        if email:
            regex = re.compile(r'.+@[A-Za-z0-9-]+\.[A-Z|a-z]{2,}')
            if not re.fullmatch(regex, email):
                flash(f"Извините, похоже что-то не так с вашим email: ({email}). Попробуйте email формата xxx@xxx.xxx")
                return redirect("/auth/register")
        if not acc_type or acc_type not in ("private", "public"):
            flash("Извините, что-то не так с вашим указанием типа учетной записи.")
            return redirect("/auth/register")

        # Add username and hash password to database
        database = get_db()

        # Get max user_id
        max_user_id = database.execute("SELECT MAX(user_id) FROM auth").fetchone()[0]
        if not max_user_id:
            max_user_id = 1
        else:
            max_user_id = max_user_id + 1

        # ----------------------- TRANSACTION -------------------------
        # Add new user to auth, broker tables

        database.isolation_level = None
        database.execute("begin")

        try:
            database.execute(
                "INSERT INTO auth "
                "(user_id, username, password_hash, email, account_type) "
                "VALUES (?, ?, ?, ?, ?)",
                (max_user_id, username, generate_password_hash(password), email, acc_type))

            database.execute("INSERT INTO broker "
                             "(user_id) VALUES (?)",
                             (max_user_id,))

            database.execute("commit")

            helpers_functions.app_log_add(f"Success. auth.py register(): Add new user to database "
                        f"user_id={max_user_id}, username={username}")

        except database.Error:
            # If username already exist
            database.execute("rollback")
            database.close()
            helpers_functions.app_log_add("Error. auth.py register(): SQL error in transaction.")
            flash(f"Извините, невозможно добавить {username} , попробуйте другое имя пользователя.")
            return redirect('/auth/register')

        # -------------------- END TRANSACTION -------------------------

        # Redirect user to login page
        return redirect("/auth/login")

    # GET request
    else:
        # Return register template
        if g.user:
            return redirect("/")
        else:
            return render_template("auth/register.html")


@bp.route("/login", methods=("POST", "GET"))
def login():
    """
    Login user
    """

    # POST request
    if request.method == "POST":

        # Forget any user_id
        session.clear()

        # Ensure username was submitted
        if not request.form.get("username"):
            flash("Извините, похоже вы забыли указать username, попробуйте еще раз.")
            return redirect("/auth/login")

        # Ensure password was submitted
        elif not request.form.get("password"):
            flash("SИзвините, похоже вы забыли указать password, попробуйте еще раз.")
            return redirect("/auth/login")

        # Query database for username
        database = get_db()

        rows = database.execute("SELECT * FROM auth "
                                "WHERE username = ?",
                                (request.form.get("username"),)).fetchall()

        # Ensure username exists and password is correct
        if len(rows) != 1:
            database.close()
            flash(f"Извините, похоже неверное имя пользователя ({request.form.get('username')}). Попробуйте еще раз. "
                  f"Если вы впервые на сайте, необходимо зарегистрироваться. (Регистрация).")
            return redirect("/auth/login")
        elif not check_password_hash(rows[0]["password_hash"], request.form.get("password")):
            database.close()
            flash("Извините, похоже вы ввели неверный пароль. Попробуйте еще раз. Если вы впервые на сайте- создайте "
                  "нового пользователя в пункте Регистрация.")
            return redirect("/auth/login")

        # Remember which user has logged in
        session["user_id"] = rows[0]["user_id"]

        database.close()

        helpers_functions.app_log_add(f"Success. auth.py login() user_id {session['user_id']} logged in.")

        # Redirect user to home page
        return redirect("/sandbox/depo")

    # GET request
    else:
        return render_template("auth/login.html")


@bp.route("/logout")
def logout():
    """
    Logout user. Forget session info.
    """
    helpers_functions.app_log_add(f"Success. auth.py logout() user_id {session['user_id']} logged out.")
    session.clear()
    return redirect("/")


@bp.before_app_request
def load_logged_in_user():
    """
    Create global variable g - as row of auth table.
    """
    user_id = session.get('user_id')
    if not user_id:
        g.user = None
    else:
        g.user = get_db().execute("SELECT * FROM auth "
                                  "WHERE user_id = ?",
                                  (user_id,)).fetchone()


def login_required(f):
    """
    Decorate routes to require login.

    https://flask.palletsprojects.com/en/1.1.x/patterns/viewdecorators/
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if g.user is None:
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)

    return decorated_function
