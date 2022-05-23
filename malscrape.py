#!/usr/bin/env python3.7
import asyncio
import logging
import logging.handlers
import re
import sqlite3
from argparse import ArgumentParser
from collections import namedtuple
from datetime import datetime, timedelta
from getpass import getpass
from typing import Sequence, Optional, List

import aiohttp

async def main():
    args = parse_cmd_args()
    username = input('Your myanimelist.net username: ')
    password = getpass('Your myanimelist.net password: ')
    for page_count in range(args.from_page, args.to_page + 1):
        await run(page_num=page_count, username=username, password=password,
                  name=args.name, older=args.older, younger=args.younger,
                  location=args.location, gender=args.gender, db_path=args.db,
                  verbose=args.verbose)
        print(f'### Done with page {page_count}/{args.to_page} ###')

def parse_cmd_args():
    parser = ArgumentParser()
    parser.add_argument("-n", "--name", dest="name", type=str, default='',
                        help="found users names must match this")
    parser.add_argument("-o", "--older", dest="older", type=int, default=0,
                        help="found users must be older than this (in years)")
    parser.add_argument("-y", "--younger", dest="younger", type=int, default=0,
                        help="found users must be younger than this (in years)")
    parser.add_argument("-l", "--location", dest="location", type=str, default='',
                        help="found users must live here")
    parser.add_argument("-g", "--gender", dest="gender", type=str, default=0,
                        help="found users must be of this gender_id (0=irrelevant, 1=male, 2=female, 3=non-binary}")
    parser.add_argument("-f", "--from", dest="from_page", type=int, default=1,
                        help="lower boundary of the search pages to scrape (boundaries are included)")
    parser.add_argument("-t", "--to", dest="to_page", type=int, default=1,
                        help="upper boundary of the search pages to scrape (boundaries are included)")
    parser.add_argument("-db", "--database", dest="db", type=str, default='users.db',
                        help="file path of the sqlite3 database")
    parser.add_argument("-v", "--verbose", action='store_true',
                        help="display every scraped user object")
    return parser.parse_args()

async def run(page_num, username, password, name, location, older, younger, gender, db_path, verbose):
    file_handler = logging.handlers.TimedRotatingFileHandler('debug.log', backupCount=10)
    file_handler.setLevel(logging.DEBUG)
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.WARNING)
    logging.basicConfig(level=logging.DEBUG, handlers=(stream_handler, file_handler))
    async with aiohttp.ClientSession() as session:
        await login(session, username, password)
        try:
            search_page = await get_search_page(session, page_num, name, location,
                                                older, younger, gender)
        except asyncio.TimeoutError:
            logging.warning(f'Ignoring TimeoutError for search page {page_num}')
            return
        user_urls = ['https://myanimelist.net' + url for url in users_from(search_page)]
        if len(user_urls) == 0:
            logging.error(f'No users could be found on page {page_num}')
        user_jobs = [page_text(session, url) for url in user_urls]
        user_pages = remove_exceptions(await asyncio.gather(*user_jobs, return_exceptions=True))
    users = []
    for page in user_pages:
        try:
            users.append(get_user_data(page))
        except Exception:
            logging.exception('Ignoring exception while scraping a user page')
        if verbose:
            print(users[-1])
    users = [u for u in users if u.name is not None]
    if len([u for u in users if u.affinity is not None]) == 0:
        logging.warning(f'No affinities could be found on page {page_num}, you might not be logged in')
    save_to_db(db_path, users)

# Helper Functions
def remove_exceptions(sequence: Sequence):
    return (item for item in sequence if not isinstance(item, Exception))

def chunks(l, n):
    """Yield successive n-sized chunks from l."""
    for i in range(0, len(l), n):
        yield l[i:i + n]


# Web Requests
async def login(session, username, password):
    async with session.get('https://myanimelist.net/login.php') as resp:
        csrf_token = re.search(r"<meta name=['\"]csrf_token['\"] content=['\"](.+?)['\"]>",
                               (await resp.text())).group(1)
    await session.post('https://myanimelist.net/login.php', data={
        'user_name': username,
        'password': password,
        'cookie': 1,
        'submit': 1,
        'sublogin': 'Login',
        'csrf_token': csrf_token,
    })

async def get_search_page(session, page_num, name, location, older, younger, gender):
    params = {
        'q': name,
        'loc': location,
        'agelow': older,
        'agehigh': younger,
        'g': gender,
        'show': str(page_num * 24),
    }
    async with session.get('https://myanimelist.net/users.php', params=params) as resp:
        return await resp.text()

async def page_text(session, url):
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            return await resp.text()
    except asyncio.TimeoutError as e:
        logging.warning(f'Ignoring asyncio.TimeoutError for {url} (known bug)')
        return e
    except Exception as e:
        logging.exception(f'Ignoring unexpected Exception for {url}')
        return e


# Scraping
def users_from(page):
    return re.findall(r'(?<=<div class="picSurround"><a href=").+?(?=">)', page)

User = namedtuple('User', ['name', 'last_online', 'gender', 'birthday', 'joined',
                           'location', 'shared', 'affinity', 'friend_count', 'days',
                           'mean_score', 'completed', 'favorites'])
Favorites = namedtuple('Favorites', ['anime', 'manga', 'character', 'people'])

def get_user_data(p) -> User:
    return User(
        name=safe_search(r"<span.*?>\s*(.*?)'s Profile", p),
        last_online=without_seconds(mal_to_datetime(safe_search(r"Last Online</span>.*?>(.*?)</span>", p))),
        gender=safe_search(r"Gender</span>.*?>(.*?)</span>", p),
        birthday=to_date(mal_to_datetime(safe_search(r"Birthday</span>.*?>(.*?)</span>", p))),
        location=safe_search(r"Location</span>.*?>(.*?)</span>", p),
        joined=to_date(mal_to_datetime(safe_search(r'Joined</span><span class="user-status-data di-ib fl-r">(.*?)<', p))),
        shared=safe_int(safe_search(r'class="fs11">(\d+?) Shared', p)),
        affinity=scrape_affinity(p),
        friend_count=safe_int(safe_search(r'All \(([\d,]+?)\)</a>Friends</h4>', p)),
        days=safe_float(safe_search(r'Anime Stats</h5>\s*<.*?>\s*<.*?><.*?>Days: </span>([\d,]+\.*\d*)</div>', p)),
        mean_score=safe_float(safe_search(r'Mean Score: </span>([\d,]+\.*\d*)', p)),
        completed=safe_int(safe_search(r'Completed</a><span class="di-ib fl-r lh10">([\d,]+)', p)),
        favorites=Favorites(anime=safe_findall(r'<div class="di-tc va-t pl8 data">\s*<a href=".+?/anime/.+?">(.+?)</a>', p),
                            manga=safe_findall(r'<div class="di-tc va-t pl8 data">\s*<a href=".+?/manga/.+?">(.+?)</a>', p),
                            character=safe_findall(r'<div class="di-tc va-t pl8 data">\s*<a href=".+?/character/.+?">(.+?)</a>', p),
                            people=safe_findall(r'<div class="di-tc va-t pl8 data">\s*<a href=".+?/people/.+?">(.+?)</a>', p),
                            ),
    )

def scrape_affinity(page):
    match = re.search(r'<div class="bar-outer-negative ar"><.*?>[-]?([-]?\d+\.*\d*)%'
                      r'.*?</span></div>\s*<div class="bar-outer-positive al"><.*?>.*?(\d+\.*\d*)%', page)
    if match:
        return float(match.group(1)) or float(match.group(2))

def safe_search(*args, **kwargs) -> Optional[str]:
    match = re.search(*args, **kwargs)
    if match is None:
        return None
    return match.group(1)

def safe_findall(*args, **kwargs) -> List[str]:
    return [m.group(1) for m in re.finditer(*args, **kwargs)]

# Helper functions
def mal_to_datetime(mal_time: str) -> Optional[datetime]:
    if not mal_time:
        return None
    # now or seconds
    if mal_time == 'Now' or 'second' in mal_time:
        return datetime.now()
    # minutes or hours
    m_or_h = re.match(r'(\d{1,2}) (minute|hour).*?', mal_time)
    if m_or_h:
        if m_or_h.group(2) == 'minute':
            return datetime.now() - timedelta(minutes=int(m_or_h.group(1)))
        return datetime.now() - timedelta(hours=int(m_or_h.group(1)))
    # today or yesterday
    t_or_y = re.match(r'(Today|Yesterday), (.+)', mal_time)
    if t_or_y:
        day = datetime.now().day - 1 if t_or_y.group(1) == 'Yesterday' else datetime.now().day
        time_ = datetime.strptime(t_or_y.group(2), '%I:%M %p')
        return datetime.now().replace(day=day, hour=time_.hour, minute=time_.minute)
    # several timestamp formats
    formats = (
        ('%b %d, %Y %I:%M %p', lambda d: d),  # full timestamp
        ('%b %d, %I:%M %p', lambda d: d.replace(year=datetime.now().year)),  # current year timestamp
        ('%b %d, %Y', lambda d: d),  # complete birthday
        ('%b %d', lambda d: d),  # birthday month and day
        ('%b', lambda d: d),  # birthday month
        ('%Y', lambda d: d),  # birthday year
    )
    for f, cleanup in formats:
        try:
            return cleanup(datetime.strptime(mal_time, f))
        except ValueError:
            pass

def without_seconds(date_time: Optional[datetime]) -> Optional[str]:
    if date_time:
        return date_time.replace(microsecond=0).isoformat(' ')[:-3]

def to_date(date_time: Optional[datetime]) -> Optional[str]:
    if date_time:
        return date_time.date().isoformat()

def safe_int(text: str) -> Optional[int]:
    if text is not None:
        return int(text.replace(',', ''))

def safe_float(text: str) -> Optional[float]:
    if text is not None:
        return float(text.replace(',', ''))


# Database
def save_to_db(db_path, users: Sequence[User]):
    db = sqlite3.connect(db_path)
    with db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS user(
            name TEXT PRIMARY KEY NOT NULL,
            last_online TEXT,
            gender TEXT,
            birthday TEXT,
            joined TEXT,
            location TEXT,
            shared INTEGER,
            affinity REAL,
            friend_count INTEGER,
            days INTEGER,
            mean_score REAL,
            completed INTEGER
        );
        CREATE TABLE IF NOT EXISTS favorite(
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            user TEXT NOT NULL REFERENCES user
        );
        CREATE UNIQUE INDEX IF NOT EXISTS favorite_index ON favorite(name, user);
        ''')
        db.executemany('REPLACE INTO user' + str(User._fields[:-1])
                       + ' VALUES (' + ('?,' * len(User._fields[:-1]))[:-1] + ') ',
                       [u[:-1] for u in users])
        for ftype in Favorites._fields:
            db.executemany(f'INSERT OR IGNORE INTO favorite VALUES(?, ?, ?)',
                           [(fname, ftype, u.name) for u in users for fname in getattr(u.favorites, ftype)])

if __name__ == '__main__':
    asyncio.run(main())
