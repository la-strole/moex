CREATE TABLE depo (
id INTEGER PRIMARY KEY AUTOINCREMENT,
user_id INTEGER NOT NULL,
ticker TEXT NOT NULL,
lotsize INTEGER NOT NULL,
name TEXT NOT NULL,
isqualifiedinvestors INTEGER NOT NULL,
initialfacevalue REAL,
number INTEGER NOT NULL,
currency TEXT NOT NULL,
market TEXT NOT NULL,
min_border REAL,
max_border REAL,
notification TEXT,
email_sent TEXT,
FOREIGN KEY (user_id) REFERENCES auth (user_id)
);
CREATE INDEX depo_user ON depo (user_id, ticker);


CREATE TABLE broker (
id INTEGER PRIMARY KEY AUTOINCREMENT,
user_id TEXT UNIQUE,
account REAL DEFAULT 100000,
FOREIGN KEY (user_id) REFERENCES auth (user_id)
);
CREATE INDEX broker_user ON broker (user_id);


CREATE TABLE auth (
user_id INTEGER PRIMARY KEY,
username TEXT UNIQUE NOT NULL,
password_hash TEXT NOT NULL,
email TEXT,
account_type TEXT
);
CREATE INDEX auth_user ON auth (username);

CREATE TABLE log (
id INTEGER PRIMARY KEY,
user_id INTEGER NOT NULL,
ticker TEXT NOT NULL,
operation TEXT NOT NULL,
price REAL,
number INTEGER,
price_total REAL,
date_time TEXT NOT NULL,
FOREIGN KEY (user_id) REFERENCES auth (user_id)
);
CREATE INDEX log_user ON log (user_id);

CREATE TABLE listing (
id INTEGER PRIMARY KEY AUTOINCREMENT,
secid TEXT NOT NULL,
secname TEXT COLLATE NOCASE
);
CREATE INDEX listing_ticker ON listing (secid);
CREATE INDEX listing_secname ON listing (secname);

CREATE TABLE app_log (
id INTEGER PRIMARY KEY AUTOINCREMENT,
log_text TEXT NOT NULL,
date_time TEXT NOT NULL
);