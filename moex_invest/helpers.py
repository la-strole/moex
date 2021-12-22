import re
import requests
import sqlite3
from datetime import datetime


class helpers_functions:
    # Get database name from __init__.py application fabric
    database_name = None
    schedule_count = 0

    @staticmethod
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
                helpers_functions.app_log_add(f"Error. helpers.py lookup.get_currency(): {e}.")
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
                helpers_functions.app_log_add(f"Error. helpers.py lookup.get_currency(): {e}.")
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
                helpers_functions.app_log_add(f'Error. helpers.py lookup.get_description(): {e}.')
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
                helpers_functions.app_log_add(f"Error. helpers.py lookup.get_description(): {e}")
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
                helpers_functions.app_log_add(f"Error. helpers.py lookup(): {e}.")
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
                    helpers_functions.app_log_add(f"Warning. helpers.py lookup(). Status index of {symbol} is "
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
                    helpers_functions.app_log_add("Error. helpers.py lookup() Can not get currency results - "
                                                  "they are empty.")
                    # if currency is important for this operation
                    if results['currencyid'] != 'rub':
                        return ['Извините, сейчас валютные операции недоступны. " \
                            "Попробуйте другой тикер. При повторении ошибки обратитесь к администратору сайта.'], None
                    else:
                        return None, results

            except (KeyError, TypeError, ValueError) as e:
                helpers_functions.app_log_add(f"Error. helpers.lookup(): {e}")
                error_messages.append(f'Извините, похоже не получается получить информацию о {symbol} '
                                      'от московской биржи. Попробуйте другой тикер, при повторении ошибки свяжитесь с '
                                      'администратором сайта.')
                return error_messages, None
        else:
            helpers_functions.app_log_add('Error. helpers.py lookup() get empty return from '
                                          'helpers.lookup.get_description() function.')
            return error_messages, None

    @staticmethod
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
            helpers_functions.app_log_add("Error. helpers.py take_symbols(): "
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
            helpers_functions.app_log_add("Error. helpers.py take_symbols(): "
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
            helpers_functions.app_log_add("Error. helpers.py take_symbols(): "
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

        database = sqlite3.connect(helpers_functions.database_name)
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
                helpers_functions.app_log_add(f"Success. helpers.py take_symbols(): "
                                              f"Add {len(tickers)} rows to database listing table.")

            except database.Error as e:
                helpers_functions.app_log_add(f"Error. helpers.py take_symbols(): SQL error in transaction {e}.")
                database.execute("rollback")
            # -------------------------END TRANSACTION ---------------------------
            database.close()

        return len(tickers)

    @staticmethod
    def check_ticker_text_fail(ticker_line: str):
        """
        Check ticker.
        :param: ticker_line: string as stock symbol.
        :return: None if ticker is letter or digit or -+= symbol else return error message.
        """
        assert isinstance(ticker_line, str)

        # ticker_line - line like "aflt Аэрофлот АО"
        # Get ticker from ticker_line
        ticker = ticker_line.split(' ')[0]

        if ticker:

            pattern = re.compile("[A-Za-z0-9+-=]+")
            if not pattern.fullmatch(ticker):
                return f"Sorry, your ticker ({ticker}) is not consists only from letters, digits and + - = symbols."
            # Alright
            return None

        else:
            return f"Sorry, your ticker ({ticker}) is empty."

    @staticmethod
    def check_count_text_fail(count: str):
        """
        Check count as a positive integer.
        :param: count: str
        :return: None if there are no errors, else return error text.
        """
        assert isinstance(count, str)
        if count:
            pattern = re.compile("[0-9]+")
            if not pattern.fullmatch(count):
                return f"Извините, ваше число ({count}) состоит не только из точки и положительных цифр."
            else:
                try:
                    int(count)
                    return None
                except ValueError:
                    return f"Похоже что-не так с вашим числом {count}"
        else:
            return f"Извините, ваше число ({count}) пусто."

    @staticmethod
    def check_float(float_line):
        """
        Check if possible to transalte string to valid float number.
        :param float_line: str
        :return: None or errors
        """

        if float_line:
            pattern = re.compile("([0-9]*[.])?[0-9]+")
            if not pattern.fullmatch(float_line):
                return f"Извините, ваше число ({float_line}) состоит не только из точки и цифр 1-9."
            else:
                try:
                    float(float_line)
                    return None
                except ValueError:
                    return f"Похоже что-то не так с вашим числом {float_line}."
        else:
            return f"Похоже ваше число ({float_line}) пусто."

    @staticmethod
    def check_final_price(price, number, results):
        """
        Get final price for results from MOEX API response. (Usually from helpers.lookup()).
        :param price: 'offer' - if you want buy something;
                      'bid' - if you want sell something;
                      'prevadmittedquote' - if you want moex cource;
        :param number: int number of lots
        :param results: dictionary from helpers.lookup()[1] - result of request to MOEX API;
        :return: float final price in rubles with eur, usd, bond, shares input. lot * current price for bonds, shares,
                 foreign shares or None.
        """

        assert price in ['bid', 'offer', 'prevadmittedquote']

        final_price = None

        if results[price]:

            # 1. Check final price

            # Check currencyid (Attention! may be more legal use results["faceunit"] on test bonds they are equal)
            currency = results["currencyid"]

            # If it is bonds
            if results["market"] == 'bonds':

                # Check initialfacevalue
                initialfacevalue = results["initialfacevalue"]
                # Check lotsize
                lotsize = results["lotsize"]
                # Check usd/eur values
                # Get final price
                if currency == 'usd':
                    final_price = int(number) * float(results[price]) * 0.01 * float(initialfacevalue) * int(
                        lotsize) * float(results['usd'])
                elif currency == 'eur':
                    final_price = int(number) * float(results[price]) * 0.01 * float(initialfacevalue) * int(
                        lotsize) * float(results['eur'])
                elif currency == 'rub' or currency == 'sur':
                    final_price = int(number) * float(results[price]) * 0.01 * float(initialfacevalue) * int(lotsize)
                else:
                    helpers_functions.app_log_add(f"Error. helpers.py check_final_price(): "
                                                  f"Can not get currency in results.")

            # If it is shares or foreign shares
            else:
                # Check lotsize
                lotsize = results["lotsize"]
                if currency == 'usd':
                    final_price = int(number) * float(results[price]) * int(lotsize) * float(results['usd'])
                elif currency == 'eur':
                    final_price = int(number) * float(results[price]) * int(lotsize) * float(results['eur'])
                elif currency == 'rub' or currency == 'sur':
                    final_price = int(number) * int(lotsize) * float(results[price])
                else:
                    helpers_functions.app_log_add(f"Error. helpers.py check_final_price(): "
                                                  f"Can not get currency in results.")

            return final_price

        return None

    @staticmethod
    def finance_format(value):
        """
        Format value as finance.
        :param value: float to format
        :return: formatted float or None
        """
        try:
            return f"{value:,.2f}"

        except ValueError:
            helpers_functions.app_log_add(f"Error. helpers.py finance_format() "
                                          f"can not convert value=({value}) to float .02")
            return None

    @staticmethod
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

        db_name = helpers_functions.database_name
        if db_name:
            database = sqlite3.connect(db_name)
            with database:
                database.execute("INSERT INTO app_log (log_text, date_time) "
                                 "VALUES (?, ?)",
                                 (message, datetime.now().isoformat()))

            database.close()

        else:
            print("Error. helpers.py app_log_add Can not get database name from class helper_functions")