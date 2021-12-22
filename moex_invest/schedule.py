"""
Schedule registered at __init__.py file and there run init().
"""
import os
import sqlite3
import pytz
import requests
import yagmail
from os import environ
from datetime import datetime


def schedule():
    database_name = 'moex.db'

    def lookup(symbol):
        """
        Look for MOEX API for ticker symbol.
        :param app_log_add: function to logged
        :param symbol: ticker: str
        :return: tuple (errors, results:dict : isqualifiedinvestors secid name faceunit initialfacevalue currencyid lotsize
        prevadmittedquote bid offer)
        """

        # Error message use for flash in client browser
        error_messages = []

        def get_currency():
            """
            Get current usd, eur fixes from MOEX API.
            :return: dictionary {'usd': value:float, 'eur':value:float}, if errors return None.
            """

            url_usd = 'https://iss.moex.com/iss/' \
                      'engines/currency/' \
                      'markets/index/' \
                      'securities/usdfix.json' \
                      '?iss.meta=off&' \
                      'iss.only=marketdata&' \
                      'marketdata.columns=CURRENTVALUE'

            url_eur = 'https://iss.moex.com/iss/' \
                      'engines/currency/' \
                      'markets/index/' \
                      'securities/eurfix.json' \
                      '?iss.meta=off&' \
                      'iss.only=marketdata&' \
                      'marketdata.columns=CURRENTVALUE'

            # Contact API
            try:
                response_usd = requests.get(url_usd)
                response_eur = requests.get(url_eur)
            except requests.RequestException as e:
                app_log_add(f"Error. schedule.py lookup.get_currency(): {e}.")
                return None

            # parse response
            try:
                usd = response_usd.json()
                eur = response_eur.json()
                return {
                    'usd': usd["marketdata"]["data"][0][0],
                    'eur': eur["marketdata"]["data"][0][0]
                }

            except (KeyError, TypeError, ValueError) as e:
                app_log_add(f"Error. schedule.py lookup.get_currency(): {e}.")
                return None

        def get_description():
            """
            Get information for depo table and future request to MOEX API for market price.
            :return tuple (error, result:dict)
            """

            # Contact API
            try:

                url = f"https://iss.moex.com/iss/securities/{symbol}.json?" \
                      f"iss.meta=off&" \
                      f"description.columns=name,value&" \
                      f"boards.columns=secid,boardid,title,market,engine,is_primary,currencyid"

                response = requests.get(url)
                response.raise_for_status()

            except requests.RequestException as e:

                error_messages.append(f'Извините, похоже не получается получить информацию о {symbol} '
                                      'от московской биржи. Попробуйте другой тикер, при повторении ошибки свяжитесь с '
                                      'администратором сайта.')
                app_log_add(f'Error. schedule.py lookup.get_description(): {e}.')
                return error_messages, None

            # Parse response
            try:
                quote = response.json()

                if quote:

                    result = {}

                    # 1. DESCRIPTION TABLE

                    # Get columns number in description table
                    name_index = quote["description"]["columns"].index("name")
                    value_index = quote["description"]["columns"].index("value")

                    # Get data from description table for future price request and depo
                    # ISQUALIFIEDINVESTORS, SECID, NAME, FACEUNIT, INITIALFACEVALUE
                    # Look for this names in description table rows
                    interesting_names = dict.fromkeys(
                        ('ISQUALIFIEDINVESTORS', 'SECID', 'NAME', 'FACEUNIT', 'INITIALFACEVALUE'))

                    for row in quote["description"]["data"]:

                        if row[name_index] in interesting_names:

                            if row[name_index] == 'INITIALFACEVALUE':
                                result[row[name_index].lower()] = float(row[value_index])
                            else:
                                result[row[name_index].lower()] = row[value_index].lower()

                    # 2. BOARDS TABLE

                    # Get columns number in description table
                    boardid_index = quote["boards"]["columns"].index("boardid")
                    market_index = quote["boards"]["columns"].index("market")
                    engine_index = quote["boards"]["columns"].index("engine")
                    is_primary_index = quote["boards"]["columns"].index("is_primary")
                    currencyid_index = quote["boards"]["columns"].index("currencyid")

                    # Get data from boards table for future price request and depo
                    # Look for primary board in boards table rows

                    for row in quote["boards"]["data"]:
                        if row[is_primary_index] == 1:
                            result["boardid"] = row[boardid_index]
                            result["engine"] = row[engine_index]
                            result["market"] = row[market_index]
                            result["currencyid"] = row[currencyid_index].lower()

                    return None, result

            except (KeyError, TypeError, ValueError) as e:
                error_messages.append(f'Извините, похоже не получается получить информацию о {symbol} '
                                      'от московской биржи. Попробуйте другой тикер, при повторении ошибки свяжитесь с '
                                      'администратором сайта.')
                app_log_add(f"Error. schedule.py lookup.get_description(): {e}")
                return error_messages, None

        results = get_description()[1]

        if results:

            # 1. Contact API
            try:
                # Get market info
                url = f"https://iss.moex.com/iss/" \
                      f"engines/{results.get('engine')}/" \
                      f"markets/{results.get('market')}/" \
                      f"boards/{results.get('boardid')}/" \
                      f"securities/{results.get('secid')}.json" \
                      f"?iss.meta=off&" \
                      f"iss.only=securities,marketdata&" \
                      f"securities.columns=LOTSIZE,STATUS,PREVADMITTEDQUOTE&" \
                      f"marketdata.columns=BID,OFFER"

                response = requests.get(url)
                response.raise_for_status()

            except requests.RequestException as e:
                app_log_add(f"Error. schedule.py lookup(): {e}.")
                error_messages.append(f'Извините, похоже не получается получить информацию о {symbol} '
                                      'от московской биржи. Попробуйте другой тикер, при повторении ошибки свяжитесь с '
                                      'администратором сайта.')

                return error_messages, None

            # Parse response
            try:

                response = response.json()

                # 1. From securities table get lot size, if it is available, PREVADMITTEDQUOTE (market price)
                lotsize_index = response["securities"]["columns"].index("LOTSIZE")
                avaliable_index = response["securities"]["columns"].index("STATUS")
                prevadmittedquote_index = response["securities"]["columns"].index("PREVADMITTEDQUOTE")

                # 2. If it is not available to buy or sell
                if response["securities"]["data"][0][avaliable_index] != 'A':
                    app_log_add(f"Warning. schedule.py lookup(). Status index of {symbol} is "
                                f"{response['securities']['data'][0][avaliable_index]}")
                    error_messages.append(
                        f"Извините, но в настоящее время {symbol} недоступен для торговли. Попробуйте другой тикер.")
                    return error_messages, None

                results["lotsize"] = response["securities"]["data"][0][lotsize_index]
                results["prevadmittedquote"] = response["securities"]["data"][0][prevadmittedquote_index]

                # 3. From market data get BID (buy price) and OFFER (sell price)
                bid_index = response["marketdata"]["columns"].index("BID")
                offer_index = response["marketdata"]["columns"].index("OFFER")

                results['bid'] = response["marketdata"]["data"][0][bid_index]
                results['offer'] = response["marketdata"]["data"][0][offer_index]

                # 4. Add currency values
                currency = get_currency()
                if currency:
                    results['usd'] = float(currency['usd'])
                    results['eur'] = float(currency['eur'])
                    return None, results
                else:
                    app_log_add("Error. schedule.py lookup() Can not get currency results - "
                                "they are empty.")
                    # if currency is important for this operation
                    if results['currencyid'] != 'rub':
                        return ['Извините, сейчас валютные операции недоступны. " \
                               "Попробуйте другой тикер. При повторении ошибки обратитесь к администратору сайта.'], None
                    else:
                        return None, results

            except (KeyError, TypeError, ValueError) as e:
                app_log_add(f"Error. schedule.lookup(): {e}")
                error_messages.append(f'Извините, похоже не получается получить информацию о {symbol} '
                                      'от московской биржи. Попробуйте другой тикер, при повторении ошибки свяжитесь с '
                                      'администратором сайта.')
                return error_messages, None
        else:
            app_log_add('Error. schedule.py lookup() get empty return from '
                        'schedule.lookup.get_description() function.')
            return error_messages, None

    def app_log_add(text: str):
        """
        Add row to app_log table of database
        :param text: text message to adding to database
        :return: None
        """
        try:
            message = str(text)
        except:
            message = 'Error. db.app_log_add() message to app_log is not string'

        db_name = database_name
        if db_name:
            database = sqlite3.connect(db_name)
            with database:
                database.execute("INSERT INTO app_log (log_text, date_time) "
                                 "VALUES (?, ?)",
                                 (message, datetime.now().isoformat()))

            database.close()

        else:
            print("Error. schedule.py app_log_add Can not get database name from class helper_functions")

    # If database don't work with pythonanywhere - delete it from update_current_prices - there are only for log

    def update_current_prices(database):
        """
        Get current bid, offer, prevadmitted price for ticker with depo.notification == true
        database: database name from app.config
        :return: sand_mail: dict of emails to send. (with email_sent = true if email already sent).
        To send mail daily, not every hour., If errors - return None.
        """

        # Get interesting data from database
        email_list = {}
        db_con = sqlite3.connect(database)
        db_con.row_factory = sqlite3.Row
        rows = db_con.execute(
            "SELECT auth.user_id, auth.email, depo.ticker, depo.min_border, depo.max_border, depo.email_sent "
            "FROM depo "
            "JOIN auth "
            "ON depo.user_id=auth.user_id "
            "WHERE notification = 'true'").fetchall()

        if rows:
            for row in rows:
                if row['ticker'] not in email_list:
                    email_list[row['ticker']] = [{'user_id': row['user_id'], 'email': row['email'],
                                                  'min_border': row['min_border'], 'max_border': row['max_border'],
                                                  'email_sent': row['email_sent']}]
                else:
                    email_list[row['ticker']].append({'user_id': row['user_id'], 'email': row['email'],
                                                      'min_border': row['min_border'], 'max_border': row['max_border'],
                                                      'email_sent': row['email_sent']})

            db_con.close()
            price_list = {}
            # For every ticker get bid or prevadmitted price from MOEX API
            for ticker in email_list.keys():
                result = lookup(ticker)[1]
                if result:

                    # If bid exist - take bid, else take prevadmitted
                    if result['bid']:
                        price_list[ticker] = result['bid']
                    elif result['prevadmittedquote']:
                        price_list[ticker] = result['prevadmittedquote']
                    else:
                        price_list[ticker] = None
                        app_log_add(f"Error. schedule.py update_current_prices(): "
                                    f"Result from moex {result} "
                                    f"for ticker {ticker} not contain bid or prevadmitted")

                else:
                    app_log_add(f"Error. schedule.py update_current_prices(): "
                                f"result from moex API for ticker {ticker} is empty")
                    continue

            # Check if ticker is not between borders
            # For each ticker in price_list look for borders in email_list
            sand_mail = []
            for ticker in price_list.keys():
                for row in email_list[ticker]:
                    row['price'] = price_list[ticker]
                    row['ticker'] = ticker
                    row['date_time'] = datetime.now(tz=pytz.timezone('Europe/Moscow'))
                    if row['min_border']:
                        if float(row['min_border']) >= float(price_list[ticker]):
                            row['course'] = 'minimal_limit'
                            sand_mail.append(row)
                    if row['max_border']:
                        if float(row['max_border']) <= float(price_list[ticker]):
                            row['course'] = 'maximum_limit'
                            sand_mail.append(row)
                    else:
                        continue

            return sand_mail

        else:
            app_log_add(f"Warning. schedule.py update_current_prices(): "
                        f"Not notification in database {database}.")
            return None

    def mail(database):
        """
        Schedule job to send email every first email immediately if borders are exceeded.
        :return: None if errors, number of sent emails if success
        """
        # Check notifications and current prices
        # Remove emails for client that already sent
        full_list = update_current_prices(database)
        if full_list:
            mail_list = full_list
        else:
            return None

        # Send email
        try:
            yag_session = yagmail.SMTP(environ.get('mail_login'), environ.get('mail_password'))
        except:
            app_log_add("Error. schedule.py first_mail(): Can not connect to gmail account.")
            return None

        text_footer = f"\n Это сообщение создано автоматически. Пожалуйста, не отвечайте на него. " \
                      f"\n С уважением, Invest app Bot. " \
                      f"{datetime.now(tz=pytz.timezone('Europe/Moscow')).today().strftime('%d.%m.%y')}"

        sent_mail_number = 0

        for row in mail_list:

            # Set email title
            text_title = f"Invest Bot {row.get('ticker').upper()} out of border"
            text_body = ''

            # Set text_body
            if row.get('course') == 'minimal_limit':
                if isinstance(row.get('date_time'), datetime):
                    text_body = f"Внимание!\n{row.get('date_time').date().strftime('%d.%m.%y')} в " \
                                f"{row.get('date_time').time().strftime('%H.%M.%S')} " \
                                f"{row.get('ticker').upper()} стоит меньше нижней границы " \
                                f"{row.get('min_border')}. Текущая стоимость {row.get('price')}."
                else:
                    text_body = f"Внимание!\n{row.get('ticker').upper()} стоит меньше нижней границы " \
                                f"{row.get('min_border')}. Текущая стоимость {row.get('price')}."
            elif row.get('course') == 'maximum_limit':
                if isinstance(row.get('date_time'), datetime):
                    text_body = f"Внимание!\n{row.get('date_time').date().strftime('%d.%m.%y')} в " \
                                f"{row.get('date_time').time().strftime('%H:%M:%S')} " \
                                f"{row.get('ticker').upper()} стоит больше верхней границы " \
                                f"{row.get('max_border')}. Текущая стоимость {row.get('price')}."
                else:
                    text_body = f"Внимание!\n{row.get('ticker').upper()} стоит больше верхней границы " \
                                f"{row.get('max_border')}. Текущая стоимость {row.get('price')}."

            # Send email
            try:
                yag_session.send(to=f"{row.get('email')}", subject=text_title, contents=text_body + text_footer)
                sent_mail_number += 1
            except:
                app_log_add(
                    f"Error. schedule.py first_mail(): Can not sen email to {row.get('email')}")
                continue

        app_log_add(f"Success. schedule.py first_mail(): "
                    f"Send {sent_mail_number} with notifications.")
        return sent_mail_number

    def take_symbols():
        """
        Take list of allowed symbols from MOEX.
        (https://iss.moex.com/iss/reference/)
        :return: Length of tickers list.
        """

        # Contact API

        base_url = "https://iss.moex.com/iss"

        tickers = {}

        # 1. Get russian shares info (https://iss.moex.com/iss/engines/stock/markets/shares/securities/columns.html)

        url = f"{base_url}/engines/stock/markets/shares/securities.json?iss.only=securities&securities.columns=SECID," \
              f"STATUS,SHORTNAME "
        response = requests.get(url)

        try:
            response.raise_for_status()
        except requests.RequestException:
            app_log_add("Error. schedule.py take_symbols(): "
                        "Can not get database update shares from MOEX.")
            return None
        # Parse response
        try:
            symbols_json = response.json()
            secid_index = symbols_json["securities"]['columns'].index('SECID')
            status_index = symbols_json["securities"]['columns'].index('STATUS')
            secname_index = symbols_json["securities"]['columns'].index('SHORTNAME')

            # Delete redundancy tickers

            for row in symbols_json['securities']['data']:
                if row[status_index] == 'A' and row[secid_index] not in tickers:
                    tickers[row[secid_index]] = row[secname_index]
        except (ValueError, TypeError):
            return None

        # 2. Get russian bonds

        url = f"{base_url}/engines/stock/markets/bonds/securities.json?iss.only=securities&securities.columns=SECID," \
              f"STATUS,SHORTNAME "
        response = requests.get(url)

        try:
            response.raise_for_status()
        except requests.RequestException:
            app_log_add("Error. schedule.py take_symbols(): "
                        "Can not get database update bonds from MOEX.")
            return None
        # Parse response
        try:
            symbols_json = response.json()
            secid_index = symbols_json["securities"]['columns'].index('SECID')
            status_index = symbols_json["securities"]['columns'].index('STATUS')
            secname_index = symbols_json["securities"]['columns'].index('SHORTNAME')

            # Delete redundancy tickers

            for row in symbols_json['securities']['data']:
                if row[status_index] == 'A' and row[secid_index] not in tickers:
                    tickers[row[secid_index]] = row[secname_index]
        except (ValueError, TypeError):
            return None

        # 3. Get foreign shares

        url = f"{base_url}/engines/stock/markets/foreignshares/" \
              f"securities.json?iss.only=securities&securities.columns=SECID,STATUS,SHORTNAME"
        response = requests.get(url)

        try:
            response.raise_for_status()
        except requests.RequestException:
            app_log_add("Error. schedule.py take_symbols(): "
                        "Can not get database update foreign shares from MOEX.")
            return None
        # Parse response
        try:
            symbols_json = response.json()
            secid_index = symbols_json["securities"]['columns'].index('SECID')
            status_index = symbols_json["securities"]['columns'].index('STATUS')
            secname_index = symbols_json["securities"]['columns'].index('SHORTNAME')

            # Delete redundancy tickers

            for row in symbols_json['securities']['data']:
                if row[status_index] == 'A' and row[secid_index] not in tickers:
                    tickers[row[secid_index]] = row[secname_index]
        except (ValueError, TypeError):
            return None

        # UPDATE DATABASE

        database = sqlite3.connect(database_name)
        database.row_factory = sqlite3.Row

        if len(tickers) > 0:

            # --------------------------TRANSACTION ----------------------------
            # Transaction - write tickets to database listing table
            database.isolation_level = None
            database.execute("begin")
            try:
                # Drop old table listing
                database.execute("DELETE FROM listing")

                # Write data to listing table
                for secid, secname in tickers.items():
                    database.execute("INSERT "
                                     "INTO listing (secid, secname) "
                                     "VALUES (?, ?)",
                                     (secid, secname))

                # Commit changes
                database.execute("commit")
                app_log_add(f"Success. schedule.py take_symbols(): "
                            f"Add {len(tickers)} rows to database listing table.")

            except database.Error as e:
                app_log_add(f"Error. schedule.py take_symbols(): SQL error in transaction {e}.")
                database.execute("rollback")
            # -------------------------END TRANSACTION ---------------------------
            database.close()

        return len(tickers)

    def update_symbols():
        """
        Update tickers list of database from MOEX for AJAX response tin quote requests.
        :return: None
        """

        ticker_number = take_symbols()

        app_log_add(f"Success. schedule.py update_symbols(): "
                    f"Scheduler Update tickers listing from MOEX API. Number = {ticker_number}")

    mail(database_name)
    update_symbols()


if __name__ == "__main__":
    schedule()
