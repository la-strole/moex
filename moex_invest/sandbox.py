"""
Trader emulation blueprint
"""

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for, jsonify
from moex_invest.auth import login_required
from moex_invest.db import get_db
from moex_invest.helpers import helpers_functions
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime
import re

bp = Blueprint('sandbox', __name__, url_prefix="/sandbox")


@bp.route("/quote", methods=("POST", "GET"))
@login_required
def quote():
    """
    Get stock quote. Buy function.
    :return: quote.html template
    """

    if request.method == "GET":
        # Realize AJAX for input ticker tag
        if 'q' in request.args:
            error_messages = helpers_functions.check_ticker_text_fail(request.args.get("q"))
            if not error_messages:
                database = get_db()
                rows = database.execute("SELECT secid, secname "
                                        "FROM listing WHERE secid LIKE ? "
                                        "OR secid LIKE ? "
                                        "LIMIT 10",
                                        (f"%{request.args.get('q')}%".upper(),
                                         f"%{request.args.get('q')}%".lower())).fetchall()
                resp = jsonify([(row["secid"] + ' ' + row["secname"]) for row in rows])
                database.close()
                return resp
            else:
                return jsonify([])
        else:
            return render_template("/sandbox/quote_get.html")

    elif request.method == "POST":

        # 1. Get data from client
        symbol = request.form.get("symbol")
        number = request.form.get("number")

        # 2. Check user data

        # Check symbol
        error_messages = helpers_functions.check_ticker_text_fail(symbol)
        if error_messages:
            flash(error_messages)
            return redirect("/sandbox/quote")

        # Check number
        error_messages = helpers_functions.check_count_text_fail(number)
        if error_messages:
            flash(error_messages)
            return redirect("/sandbox/quote")

        # 3. Get information from MOEX API

        api_response = helpers_functions.lookup(symbol.split(' ')[0])
        results = api_response[1]
        errors = api_response[0]

        # If there are errors
        if not results:
            flash(','.join(errors))
            return redirect('/sandbox/quote')

        # If there are not sell offer
        if not results["offer"]:
            flash(
                f"Извините, но сейчас нет предложений о продаже {symbol}. Возможно, биржа закрыта, уточните режм "
                f"работы московской биржи или выберите более популярный тикер.")
            return redirect('/sandbox/quote')

        # 4. Check final price

        final_price = helpers_functions.check_final_price('offer', number, results)
        lotsize = results["lotsize"]

        # 5. Check broker account

        database = get_db()
        user_account = \
            database.execute("SELECT account FROM broker WHERE user_id = ?", (g.user['user_id'],)).fetchone()[0]

        if not user_account:
            helpers_functions.app_log_add(f"Error. sandbox.py quote(): user_id ({g.user['user_id']}) "
                                          f"account from broker table from "
                                          f"database is empty.")
            flash("Извините, что-то не так с вашим счетом. Повторите попытку и при неудаче обратитесь к "
                  "администратору сайта")
            return redirect("/sandbox/quote")

        # If user can not afford this
        if float(user_account) < final_price:
            flash(f"Извините, похоже на вашем счету не хватает средств для покупки "
                  f"{lotsize} {symbol} по рыночной цене {results['offer']}. "
                  f"Необходимо {helpers_functions.finance_format(final_price)}, "
                  f"у вас в наличии {helpers_functions.finance_format(user_account)}.")
            return redirect("/sandbox/quote")

        # 6. Make transaction to DB

        # Check if this user already has this type of stock (ticket variable)
        database = get_db()
        user_ticker_count = database.execute("SELECT COUNT(*) "
                                             "FROM depo "
                                             "WHERE user_id = ? AND ticker = ?",
                                             (g.user['user_id'], results['secid'])).fetchone()[0]

        database.isolation_level = None  # ON autocommit mode. Hand control of transaction-to group rollback

        # -------------------------------TRANSACTION----------------------------
        database.execute("begin")
        try:

            # 1 Add stock to depo table

            if user_ticker_count > 0:
                # If there are more than 1 row for user ticker - raise error
                assert user_ticker_count == 1, "Error with number of users rows in depo table in database"
                # User has this type of stock - increase share column
                database.execute("UPDATE depo SET number = number + ? "
                                 "WHERE user_id = ? "
                                 "AND ticker = ?",
                                 (int(number) * int(lotsize), g.user['user_id'], results['secid']))
            else:
                # User does not have this type of stock - add new row to depo table
                database.execute("INSERT INTO depo (user_id, ticker, lotsize, name, isqualifiedinvestors, "
                                 "initialfacevalue, number, currency, market, email_sent) "
                                 "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                 (g.user['user_id'], results["secid"], lotsize, results['name'],
                                  results['isqualifiedinvestors'],
                                  results.get('initialfacevalue'), int(number) * int(lotsize), results["currencyid"],
                                  results['market'], False))

            # 2 Decrease cash from users table
            database.execute("UPDATE broker "
                             "SET account = account - ?"
                             "WHERE user_id = ?",
                             (final_price, g.user['user_id']))

            # 3 Add this purchase to log table
            database.execute("INSERT "
                             "INTO log (user_id, ticker, operation, price, price_total, number, date_time)"
                             "VALUES (?,?,?,?,?,?,?)",
                             (g.user['user_id'], results['secid'], 'buy', results['offer'], final_price,
                              int(number) * int(lotsize), datetime.now().isoformat()))

            # 4 Commit transaction changes
            database.execute("commit")
            helpers_functions.app_log_add(f"Success. sandbox.py quote(): Userid {g.user['user_id']} make purchase.")

        except database.Error as e:
            database.execute("rollback")
            database.close()
            helpers_functions.app_log_add(f"Error. sandbox.py quote(): sqlite3 in TRANSACTION: {e}")

        # -----------------------END TRANSACTION ----------------------

        flash(f"Вы успешно приобрели {int(number) * int(lotsize)} единиц(у) {results['secid']} "
              f"по цене {results['offer']} на общую сумму "
              f"{helpers_functions.finance_format(final_price)} \u20bd. "
              f"Остаток на брокерском счете "
              f"{helpers_functions.finance_format((user_account - final_price))} \u20bd.")

        return redirect("/sandbox/depo")

    else:
        helpers_functions.app_log_add(f"Error. sandbox.py quote(): error with request methos qoute().")


@bp.route("/depo", methods=("POST", "GET"))
@login_required
def depo():
    """
    Depo info.
    :return: depo.html template
    """

    # If request GET - show html
    if request.method == "GET":

        # 1. Get users tickers
        total = 0
        tickers = []
        market_translate = {'shares': "акции", "foreignshares": "иностранные акции", "bonds": "облигации"}
        database = get_db()
        rows = database.execute(
            "SELECT ticker, name, initialfacevalue, number, market, min_border, max_border, notification "
            "FROM depo "
            "WHERE user_id = ?", (g.user['user_id'],)).fetchall()
        for row in rows:
            item = {'ticker': row['ticker'], 'name': row['name'], 'number': row['number'],
                    'market': market_translate.get(row['market']), 'min_border': row['min_border'],
                    'max_border': row['max_border'], 'notification': row['notification']}
            # Get info from depo table

            # 2. For each ticker get actual info from moex api
            api_response = helpers_functions.lookup(item['ticker'])

            results = api_response[1]
            errors = api_response[0]

            # If there are errors
            if not results:
                helpers_functions.app_log_add(f"Error. sandbox.py depo(): "
                                              f"Can not get result from MOEX API ticker {item['ticker']}.")
                continue
            else:
                # Get current price if BIDd exist. If not - current price is admitted price (market course prev day)
                if results['bid']:
                    item['current_price'] = results['bid']
                else:
                    item['current_price'] = results['prevadmittedquote']

                # Get final price as admitted MOEX price (market cource) * number of shares from depo table
                if results['bid']:
                    if results['lotsize']:
                        item['final_price'] = helpers_functions.check_final_price('bid', item['number'],
                                                                results) / results['lotsize']
                    else:
                        print(f"Error. sandbox.depo(): results['lotsize'] for ticker {results['secid']} is empty")
                        item['final_price'] = 0
                else:
                    if results['lotsize']:
                        item['final_price'] = helpers_functions.check_final_price('prevadmittedquote', item['number'],
                                                                results) / results[
                                                  'lotsize']
                    else:
                        print(f"Error. sandbox.depo(): results['lotsize'] for ticker {results['secid']} is empty")
                        item['final_price'] = 0

                # Get currency symbol on primary board for ticker
                item['currency_symbol'] = results['currencyid']

                # Append ticker to tickers list
                tickers.append(item)

                # Increase total value
                total += item['final_price']

        # Get user cash from broker table
        cash = database.execute("SELECT account FROM broker WHERE user_id = ?", (g.user['user_id'],)).fetchone()[0]

        # Increase total with cash
        total += float(cash)

        # 3. Return index.html with JINJA (cash, total, ticker{ticker, name, number, market, current_price, 
        # final_price, min_boarder, max_boarder, notification})

        return render_template("/sandbox/depo.html", cash=cash, total=total, tickers=tickers)

    # If request POST - change DB notification borders
    if request.method == "POST":
        # 1. Get user data
        ticker_dict = {}
        for i in request.form.items():
            line = i[0].split(' ')
            if len(line) == 2:
                ticker = line[1]
                if ticker not in ticker_dict:
                    # [min_border, max_border, check_notify]
                    ticker_dict[ticker] = [None, None, 'false']
                if line[0] == "min_border":
                    ticker_dict[ticker][0] = i[1]
                elif line[0] == 'max_border':
                    ticker_dict[ticker][1] = i[1]
                elif line[0] == 'check_notify':
                    if not i[1]:
                        ticker_dict[ticker][2] = 'false'
                    elif i[1] == 'true':
                        ticker_dict[ticker][2] = i[1]
                    else:
                        print(f"Error. sandbox.depo() while POST request check is not true or '' check is {i[1]}")
                        flash(f"Извините, похоже что-то не так с границами уведомлений. Повторите еще раз. "
                              f"Если ошибка повторится свяжитесь с администратором сайта.")
                        return redirect("/sandbox/depo")
                else:
                    print(f"Error. sandbox.depo() while POST request check min, max name from form is {line[0]}")
                    flash(f"Извините, похоже что-то не так с границами уведомлений. Повторите еще раз. "
                          f"Если ошибка повторится свяжитесь с администратором сайта.")
                    return redirect("/sandbox/depo")

            else:
                print(f"Error. sandbox.depo() while POST request check min, max name from form line is {line}")
                flash(f"Извините, похоже что-то не так с границами уведомлений. Повторите еще раз. "
                      f"Если ошибка повторится свяжитесь с администратором сайта.")
                return redirect("/sandbox/depo")

        # 2. Check user data

        # Check email exist
        if not g.user['email']:
            print(f"Error. sandbox.depo(): user (userid={g.user['user_id']}) don't set email")
            flash("Извините, но похоже вы не указали email. Измените это в меню Настройки.")
            return redirect("/sandbox/depo")

        # 3. Make changes in DB with borders and notification
        errors = []
        database = get_db()
        with database:
            # Check min max border values
            for ticker in ticker_dict.keys():
                # If min border exist
                if (ticker_dict.get(ticker))[0]:
                    error_message = helpers_functions.check_float((ticker_dict.get(ticker))[0])
                    if error_message:
                        errors.append(error_message)
                        continue
                    else:
                        (ticker_dict.get(ticker))[0] = float((ticker_dict.get(ticker))[0])
                # If max border exist
                if (ticker_dict.get(ticker))[1]:
                    error_message = helpers_functions.check_float((ticker_dict.get(ticker))[1])
                    if error_message:
                        errors.append(error_message)
                        continue
                    else:
                        (ticker_dict.get(ticker))[1] = float((ticker_dict.get(ticker))[1])
                # If both boarders exist check min < max
                if (ticker_dict.get(ticker))[0] and (ticker_dict.get(ticker))[1]:
                    if (ticker_dict.get(ticker))[0] > (ticker_dict.get(ticker))[1]:
                        errors.append(
                            f"Похоже для тикера {ticker} максимальная граница ({(ticker_dict.get(ticker))[1]})"
                            f" меньше минимальной ({(ticker_dict.get(ticker))[0]}).")
                        continue
                # Check if at least one border exist
                if not (ticker_dict.get(ticker))[0] and not (ticker_dict.get(ticker))[1] \
                        and (ticker_dict.get(ticker))[2] == 'true':
                    errors.append(f"Похоже для тикера {ticker} не указаны ни максимальная граница, ни минимальная.")
                    continue

                try:
                    database.execute("UPDATE depo "
                                     "SET min_border = ?, max_border = ?, notification = ?, email_sent = ?"
                                     "WHERE user_id = ? AND ticker = ?",
                                     ((ticker_dict.get(ticker))[0], (ticker_dict.get(ticker))[1],
                                      (ticker_dict.get(ticker))[2], False,
                                      g.user['user_id'], ticker))

                except database.Error as e:
                    print(f"Error. sandbox.depo() sqlite3: {e}")
                    errors.append("Похоже при обновлении границ возникли ошибки. Проверьте правильность и "
                                  "при необходимости свяжитесь с администратором сайта.")
                    break

        # 4. Return new depo with flash message
        flash(f"Данные по границам обновлены. {' '.join(errors)}")
        helpers_functions.app_log_add(f"Success. sandbox.py depo() userid={g.user['user_id']} "
                                      f"updated borders with depo POST request.")
        return redirect("/sandbox/depo")


@bp.route("/sell", methods=["POST", "GET"])
@login_required
def sell():
    """
    Sell function.
    :return: template sell.html
    """

    if request.method == "GET":

        # 1. Get user's ticker from database
        tickers = []
        database = get_db()
        rows = database.execute("SELECT ticker, name, number "
                                "FROM depo "
                                "WHERE user_id = ?",
                                (g.user['user_id'],)).fetchall()
        for row in rows:
            tickers.append({'ticker': row['ticker'], 'name': row['name'], 'number': row['number']})

        # 2. Check if there are get args preselect (for 'sell' click in depo table html)
        if 'q' in request.args:
            client_ticker = request.args.get('q')
            # Check user ticker
            error_message = helpers_functions.check_ticker_text_fail(client_ticker)
            if error_message:
                flash(error_message)
                return redirect("/sandbox/sell")
            elif client_ticker not in [item.get('ticker') for item in tickers]:
                flash(f"Извините, похоже у вас нет тикера {client_ticker}. Попробуйте выбрать тикер из списка.")
                return redirect("/sandbox/sell")
            else:
                return render_template("/sandbox/sell.html", tickers=tickers,
                                       client_ticker=client_ticker.lower(), ticker_exist='true')

        # 3. Format template with jinja
        return render_template("/sandbox/sell.html", tickers=tickers, client_ticker=None, ticker_exist='false')

    if request.method == "POST":

        # 1. Get data from client

        ticker = request.form.get("ticker")
        number = request.form.get("number")

        # 2. Check user data

        # Check ticker
        try:
            assert isinstance(ticker, str)
        except AssertionError:
            flash(f"Извините, похоже что-то не так с вашим тикером {ticker}. Попробуйте еще раз и в случае "
                  f"необходимости свяжитесь с администратором сайта.")
            return redirect("/sandbox/sell")

        ticker = ticker.split(' ')[0]  # line is 'ticker + name'
        error_messages = helpers_functions.check_ticker_text_fail(ticker)
        if error_messages:
            flash(error_messages)
            return redirect("/sandbox/sell")

        # Check number
        error_messages = helpers_functions.check_count_text_fail(number)
        if error_messages:
            flash(error_messages)
            return redirect("/sandbox/sell")

        # 3. Get actual information from  MOEX API

        api_response = helpers_functions.lookup(ticker)

        results = api_response[1]
        errors = api_response[0]

        # If there are errors
        if not results:
            flash(','.join(errors))
            return redirect('/sandbox/sell')

        # If there are not BID
        if not results["bid"]:
            flash(
                f"Извините, но сейчас нет предложений о покупке {ticker}. Возможно, биржа закрыта, уточните режм "
                f"работы московской биржи или выберите более популярный тикер.")
            return redirect('/sandbox/sell')

        # 4. Check final price

        final_price = helpers_functions.check_final_price('bid', number, results)
        lotsize = results["lotsize"]

        # 5. Check user depo

        database = get_db()
        row = database.execute("SELECT number "
                               "FROM depo "
                               "WHERE user_id = ? AND ticker = ?",
                               (g.user['user_id'], results['secid'])).fetchone()
        if not row:
            flash(f"Похоже вы пытаетесь продать тикер {ticker}, которого нет у вас в депозитарии. "
                  f"Проверьте депозитарий, в случае необходимости обратитесь к администратору сайта.")
            return redirect("/sandbox/sell")

        depo_number = row['number']

        if not depo_number:
            helpers_functions.app_log_add(f"Error. sandbox.py sell(): can not get number from depo table from "
                        f"database for ticker {ticker}")
            flash("Извините, невозможно получить количество ценных бумаг из депозитария. "
                  "Попробуйте еще раз, при повторении ошибки свяжитесьс администратором сайта.")
            return redirect("/sandbox/sell")

        # If user can not afford this
        if depo_number < int(number) * lotsize:
            flash(f"Извините, похоже у вас не хватает ценных бумаг для продажи "
                  f"{number} лота(ов) {ticker}. "
                  f"Необходимо {lotsize * int(number)} ед., "
                  f"у вас в наличии {depo_number} ед.")
            return redirect("/sandbox/sell")

        # 6. Make transaction to DB
        database = get_db()
        database.isolation_level = None  # ON autocommit mode. Hand control of transaction-to group rollback

        # -------------------------TRANSACTION----------------------------
        database.execute("begin")
        try:
            # 1. Add cash to user's broker account
            database.execute("UPDATE broker "
                             "SET account = account + ? "
                             "WHERE user_id = ?",
                             (final_price, g.user['user_id']))

            # 2. Check if depo number is equal number - then delete row from depo table
            if depo_number == lotsize * int(number):
                database.execute("DELETE FROM depo "
                                 "WHERE ticker = ?",
                                 (results['secid'],))
            # 3. Decrease number of shares in depo table
            else:
                database.execute("UPDATE depo "
                                 "SET number = number - ? "
                                 "WHERE ticker = ?",
                                 (lotsize * int(number), results['secid']))

            # 4. Add this purchase to log table
            database.execute("INSERT "
                             "INTO log (user_id, ticker, operation, price, price_total, number, date_time)"
                             "VALUES (?,?,?,?,?,?,?)",
                             (g.user['user_id'], results['secid'], 'sell', results['bid'], final_price,
                              int(number) * int(lotsize), datetime.now().isoformat()))

            # 5. Commit transaction changes
            database.execute("commit")
            helpers_functions.app_log_add(f"Success. sandbox.py sell(): "
                                          f"userid({g.user['user_id']}) make a deal with {ticker}.")

        except database.Error as e:

            database.execute("rollback")
            database.close()
            helpers_functions.app_log_add(f"Error. sandbox.py sell(): userid({g.user['user_id']}) "
                                          f"ticker: {ticker}. SQL error {e}.")

        # ------------------------END TRANSACTION ----------------------

        flash(f"Вы успешно продали {int(number) * int(lotsize)} единиц(у) {results['secid']} "
              f"по цене {results['bid']} на общую сумму {helpers_functions.finance_format(final_price)} \u20bd.")

        return redirect("/sandbox/depo")

    else:
        helpers_functions.app_log_add(f"Error sandbox.py sell(): "
                                      f"userid({g.user['user_id']}) request is not POST or GET.")


@bp.route("/history")
@login_required
def history():
    """
    Show history for current user from log table of database.
    :return: history.html template
    """
    tickers = []

    # Get history info from database
    database = get_db()
    rows = database.execute("SELECT ticker, operation, price, number, date_time "
                            "FROM log "
                            "WHERE user_id = ? "
                            "ORDER BY date_time DESC",
                            (g.user['user_id'],)).fetchall()

    for row in rows:
        if row['operation'] in ('buy', 'sell'):
            try:
                date_time = datetime.fromisoformat(row['date_time'])
                date = f"{date_time.date().day:02d}.{date_time.date().month:02d}.{date_time.date().year}"
                time = f"{date_time.time().hour:02d}:{date_time.time().minute:02d}:{date_time.time().second:02d}"
            except ValueError:
                date = ''
                time = ''
            tickers.append({'ticker': row['ticker'].upper(), 'operation': row['operation'], 'number': row['number'],
                            'price': row['price'], 'date': date, 'time': time})

    return render_template("/sandbox/history.html", tickers=tickers)


@bp.route("/settings", methods=["POST", "GET"])
@login_required
def settings():
    """
    Show settings for current user anf change database.
    :return: settings.html template
    """

    def get_user_account():
        """
        Get user broker account from database
        :return: account:float or '' if user account is public or if there are errors
        """
        # Get current account
        if g.user['account_type'] == 'private':
            database = get_db()
            row = database.execute("SELECT account "
                                   "FROM broker "
                                   "WHERE user_id = ?",
                                   (g.user['user_id'],)).fetchone()
            if row:
                account = row['account']
            else:
                helpers_functions.app_log_add(f"Error. sandbox.py settings.get_user_account(): "
                                              f"sqlite3: Can not get account from "
                                              f"broker table for userid={g.user['user_id']}")
                account = ''
        else:
            account = ''

        return account

    if request.method == "GET":
        # Get current account
        user_account = get_user_account()
        if user_account:
            return render_template("/sandbox/settings.html",
                                   account=helpers_functions.finance_format(user_account))
        else:
            return render_template("/sandbox/settings.html", account='')

    if request.method == "POST":

        # 1. Get client data

        name = request.form.get('name')
        password = request.form.get('password')
        new_password = request.form.get('new_password')
        new_password_conf = request.form.get('new_password_conf')
        email = request.form.get('email')
        account = request.form.get('account')
        delete_acc = request.form.get('delete_acc')

        # 2. Check client data

        # Check name
        if name and len(name) > 20:
            flash(f"Извините, похоже  ваше имя пользователя ({name}) длиннее 20 символов.")
            return redirect("/sandbox/settings")

        # Check password
        if any((password, new_password, new_password_conf)):
            if not all((password, new_password, new_password_conf)):
                flash("Извините, при смене пароля необходимо указать старый, новый, и подтвердить новый. Проверьте, "
                      "что вы это сделали.")
                return redirect("/sandbox/settings")
            else:
                # If new_password and conformation are equal
                if new_password != new_password_conf:
                    flash("Извините, похоже новый пароль не совпадает с подтверждением. Проверьте, что они одинаковы.")
                    return redirect("/sandbox/settings")

                # If passwords length > 20
                elif len(new_password) > 20:
                    flash("Извините, длина пароля ограничена 20 символами.")
                    return redirect("/sandbox/settings")

                # Check old user's password from database (g.user)
                elif not check_password_hash(g.user['password_hash'], password):
                    flash("Извините, похоже вы ввели неправильный старый пароль. Попробуйте еще раз.")
                    return redirect("/sandbox/settings")

        # Check email
        if email:
            regex = re.compile(r'.+@[A-Za-z0-9-]+\.[A-Z|a-z]{2,}')
            if not re.fullmatch(regex, email):
                flash(f"Извините, похоже что-то не так с вашим email: ({email}). Попробуйте email формата xxx@xxx.xxx")
                return redirect("/sandbox/settings")

        # Check account
        if account:
            errors = helpers_functions.check_count_text_fail(account)
            if errors:
                flash(errors)
                return redirect("/sandbox/settings")
            if g.user['account_type'] != 'private':
                flash(f"Извините, только пользователи с аккаунтом private могут изменять свой счет. "
                      f"Ваш аккаунт {g.user['account_type']}")
                return redirect("/sandbox/settings")

        # Check delete acc
        if delete_acc:
            if delete_acc != 'true':
                flash(f"Извините, похоже что-то не так с удаление вашего аккаунта.")
                return redirect("/sandbox/settings")

        # 3. Change database

        flash_messages = []
        database = get_db()
        # ---------------------------TRANSACTION -----------------------------------
        database.isolation_level = None
        database.execute("begin")
        try:

            # 1. Change username
            if name:
                database.execute("UPDATE auth "
                                 "SET username = ? "
                                 "WHERE user_id = ?",
                                 (name, g.user['user_id']))
                flash_messages.append("Имя обновлено.")
            # 2. Change password
            if new_password:
                database.execute("UPDATE auth "
                                 "SET password_hash = ? "
                                 "WHERE user_id = ?",
                                 (generate_password_hash(new_password), g.user['user_id']))
                flash_messages.append("Пароль обновлен.")
            # 3. Change email
            if email:
                database.execute("UPDATE auth "
                                 "SET email = ? "
                                 "WHERE user_id = ?",
                                 (email, g.user['user_id']))
                flash_messages.append("Email обновлен.")
            # 4. Change account
            if account:
                database.execute("UPDATE broker "
                                 "SET account = ? "
                                 "WHERE user_id = ?",
                                 (account, g.user['user_id']))
                flash_messages.append("Баланс обновлен.")
            # 5. Delete acc
            if delete_acc == 'true':
                database.execute("DELETE FROM auth WHERE user_id = ?", (g.user['user_id'],))
                database.execute("DELETE FROM depo WHERE user_id = ?", (g.user['user_id'],))
                database.execute("DELETE FROM broker WHERE user_id = ?", (g.user['user_id'],))
                flash_messages = [f"Аккаунт и вся информация о {g.user['username']} удалены."]
            # 6. commit transaction changes
            database.execute("commit")
            helpers_functions.app_log_add(f"Success. sandbox.py setting(): "
                                          f"Update settings for user_id=({g.user['user_id']}).")

        except database.Error as e:

            database.execute("rollback")
            database.close()
            helpers_functions.app_log_add(f"Error. sandbox.py setting(): "
                                          f"user_id=({g.user['user_id']}) sqlite3 TRANSACTION: {e}.")

        # ---------------------------END TRANSACTION --------------------------

        flash(' '.join(flash_messages))

        return redirect("/auth/login")


@bp.route("/rates")
@login_required
def rates():
    """
    Rates table for users with public account type.
    :return: rates.html template
    """

    if g.user['account_type'] != 'public':
        flash("Извините, рейтинги доступны только пользователям с аккаунтом типа public.")
        return redirect("/sandbox/depo")

    # Return render_template("/sandbox/rates.html")
    # 1. Cash summary
    # Get current price for every distinct ticker in depo table, create dictionary
    database = get_db()
    tickers_price = dict.fromkeys(
        [row['ticker'] for row in database.execute("SELECT DISTINCT depo.ticker "
                                                   "FROM depo "
                                                   "JOIN auth ON "
                                                   "depo.user_id=auth.user_id "
                                                   "WHERE auth.account_type = 'public'").fetchall()])
    for ticker in tickers_price:
        results = helpers_functions.lookup(ticker)[1]
        if results:
            if results.get('bid') and results.get('lotsize'):
                price = helpers_functions.check_final_price('bid', 1, results) / results['lotsize']
                tickers_price[ticker] = price
            elif results.get('prevadmittedquote') and results.get('lotsize'):
                price = helpers_functions.check_final_price('prevadmittedquote', 1, results) / results['lotsize']
                tickers_price[ticker] = price
            else:
                helpers_functions.app_log_add(f"Error. sandbox.py rates(): user_id={g.user['user_id']}, "
                            f"Can not get response from helpers.lookup for ticker {ticker}.")
                flash("Извините, сейчас рейтинги не доступны. Повторите попытку позднее, в случае поворения ошибки "
                      "обратитесь к администратору сайта.")
                return redirect("/sandbox/depo")
        else:
            helpers_functions.app_log_add(f"Error. sandbox.py rates(): Can not get lotsize, "
                                          f"bid or prevadmittedquote from helpers.lookup "
                                          f"for ticker {ticker}.")
            flash("Извините, сейчас рейтинги не доступны. Повторите попытку позднее, в случае поворения ошибки "
                  "обратитесь к администратору сайта.")
            return redirect("/sandbox/depo")

    # For each user calculate total cash
    # Get list of users like dict 'user_id' : 'username'
    users_list = {}
    rows = database.execute("SELECT user_id, username "
                            "FROM auth "
                            "WHERE account_type='public'").fetchall()
    for row in rows:
        users_list[row['user_id']] = {'username': row['username'], 'total_cash': 0, 'diversity': 0}

    # Get user_id, ticker, number from depo table of database
    for user_id in users_list:
        total_cash = 0
        rows = database.execute("SELECT ticker, number FROM depo WHERE user_id = ?",
                                (user_id,)).fetchall()

        users_list[user_id]['diversity'] = len(rows)

        for row in rows:
            total_cash += row['number'] * tickers_price[row['ticker']]

        bank_account = database.execute("SELECT account FROM broker WHERE user_id = ?", (user_id,)).fetchone()

        if bank_account:
            users_list[user_id]['total_cash'] = total_cash + bank_account['account']
        else:
            helpers_functions.app_log_add(f"Error. sandbox.py rates(): user_id={g.user['user_id']} "
                        f"sqlite3: Can not get broker account data.")
            flash("Извините, сейчас рейтинги не доступны. Повторите попытку позднее, в случае поворения ошибки "
                  "обратитесь к администратору сайта.")
            return redirect("/sandbox/depo")

    # 2. Diversity count : Get number of different tickers for each user. look at return jinja variable.

    # 3. Volume of purchases
    # Add diversity and diversity summary to users_list dict
    for user_id in users_list:
        volume_purchase = 0
        rows = database.execute("SELECT price, number, price_total "
                                "FROM log "
                                "WHERE user_id = ?",
                                (user_id,)).fetchall()
        # From log table for each user get number of sell-buy operations
        users_list[user_id]['purchase_number'] = len(rows)
        for row in rows:
            # For each user from log get summ of sell/buy
            volume_purchase += row['price_total']

        users_list[user_id]['purchase_value'] = volume_purchase
    # Send top 10 to table as jinja template in return as purchase_number
    # Send top 10 to table in jinja template when return as cash_sum
    # Send top 10 to table as jinja template in return as purchase_value
    # Send top 10 to table in jinja template when return as diversity_rate
    return render_template("/sandbox/rates.html",
                           cash_sum=sorted(list(users_list.values()), key=lambda x: x['total_cash'], reverse=True)[:10],
                           diversity_rate=sorted(list(users_list.values()), key=lambda x: x['diversity'],
                                                 reverse=True)[:10],
                           purchase_value=sorted(list(users_list.values()), key=lambda x: x['purchase_value'],
                                                 reverse=True)[:10],
                           purchase_number=sorted(list(users_list.values()), key=lambda x: x['purchase_number'],
                                                  reverse=True)[:10])
