"""
Schedule registered at __init__.py file and there run init().
"""

from moex_invest.helpers import helpers_functions

import sqlite3
import pytz
import yagmail
from os import environ
from datetime import datetime


def schedule():
    database = helpers_functions.database_name
    helpers_functions.schedule_count = (helpers_functions.schedule_count + 1) % 24

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
                result = helpers_functions.lookup(ticker)[1]
                if result:

                    # If bid exist - take bid, else take prevadmitted
                    if result['bid']:
                        price_list[ticker] = result['bid']
                    elif result['prevadmittedquote']:
                        price_list[ticker] = result['prevadmittedquote']
                    else:
                        price_list[ticker] = None
                        helpers_functions.app_log_add(f"Error. schedule.py update_current_prices(): "
                                                      f"Result from moex {result} "
                                                      f"for ticker {ticker} not contain bid or prevadmitted")

                else:
                    helpers_functions.app_log_add(f"Error. schedule.py update_current_prices(): "
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
            helpers_functions.app_log_add(f"Warning. schedule.py update_current_prices(): "
                                          f"Not notification in database {database}.")
            return None

    def first_mail(database):
        """
        Schedule job to send email every first email immediately if borders are exceeded.
        :return: None if errors, number of sent emails if success
        """
        # Check notifications and current prices
        # Remove emails for client that already sent
        full_list = update_current_prices(database)
        if full_list:
            mail_list = [item for item in full_list if item['email_sent'] == '0']
        else:
            return None

        # Send email
        try:
            yag_session = yagmail.SMTP(environ.get('mail_login'), environ.get('mail_password'))
        except:
            helpers_functions.app_log_add("Error. schedule.py first_mail(): Can not connect to gmail account.")
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
                helpers_functions.app_log_add(
                    f"Error. schedule.py first_mail(): Can not sen email to {row.get('email')}")
                continue

        # Update database depo email_sent = true
        db_con = sqlite3.connect(database)
        db_con.row_factory = sqlite3.Row
        with db_con:
            for row in mail_list:
                try:
                    db_con.execute("UPDATE depo "
                                   "SET email_sent = ? "
                                   "WHERE user_id = ? AND ticker = ?",
                                   (True, row['user_id'], row['ticker']))
                except sqlite3.Error as e:
                    helpers_functions.app_log_add(f"Error. schedule.py first_mail(): "
                                                  f"Can not set emil_sent on depo table ({e})")
                    continue
        db_con.close()

        helpers_functions.app_log_add(f"Success. schedule.py first_mail(): "
                                      f"Send {sent_mail_number} with notifications.")
        return sent_mail_number

    def second_mail(database):
        """
        Schedule job to send second etc email every day if borders are exceeded. Not every hour.
        :return: None or number of sent emails.
        """

        # Check notifications and current prices
        full_list = update_current_prices(database)
        if full_list:
            mail_list = [item for item in full_list if item['email_sent'] != '0']
        else:
            return None

        # Send email
        try:
            yag_session = yagmail.SMTP(environ.get('mail_login'), environ.get('mail_password'))
        except:
            helpers_functions.app_log_add(f"Error. schedule.first_mail() Can not connect to gmail account.")
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
                helpers_functions.app_log_add(f"Error. schedule.first_mail(): Can not sen email to {row.get('email')}")
                continue

        helpers_functions.app_log_add(
            f"Success. schedule.py second_mail(): Send {sent_mail_number} with notifications.")
        return sent_mail_number

    def update_symbols():
        """
        Update tickers list of database from MOEX for AJAX response tin quote requests.
        :return: None
        """

        ticker_number = helpers_functions.take_symbols()

        helpers_functions.app_log_add(f"Success. schedule.py update_symbols(): "
                                      f"Scheduler Update tickers listing from MOEX API. Number = {ticker_number}")

    first_mail(database)
    if helpers_functions.schedule_count == 23:
        second_mail(database)
        update_symbols()


if __name__ == "__main__":
    schedule()
