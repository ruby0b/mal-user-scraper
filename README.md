# MyAnimeList.net User Scraper
Scrapes information from [myanimelist.net](https://myanimelist.net/) profile pages and saves it into an sqlite3 database.
# Disclaimer
This is an inofficial script so you could get banned if you scrape to many pages of users because the script logs you in and out for every scraped search page.
So far no issues were reported but use this at your own risk!
# Requirements
* [Python](https://www.python.org/) version 3.7 or higher
* [aiohttp](https://pypi.org/project/aiohttp/) library
* A myanimelist.net account
* (Probably) some way to view the sqlite3 database (I recommend [DB Browser for SQLite](https://sqlitebrowser.org/))
# Usage
1. Run `malscrape.py` with python 3.7 (for command line arguments, view below) (You might want to make it executable using `chmod +x malscrape.py`)
2. Input your username and password when asked
3. The scraped data will be saved in an sqlite3 database
# Command Line Arguments
```
usage: malscrape.py [-h] [-n NAME] [-o OLDER] [-y YOUNGER] [-l LOCATION]
                    [-g GENDER] [-f FROM_PAGE] [-t TO_PAGE] [-db DB] [-v]

optional arguments:
  -h, --help            show this help message and exit
  -n NAME, --name NAME  found users names must match this
  -o OLDER, --older OLDER
                        found users must be older than this (in years)
  -y YOUNGER, --younger YOUNGER
                        found users must be younger than this (in years)
  -l LOCATION, --location LOCATION
                        found users must live here
  -g GENDER, --gender GENDER
                        found users must be of this gender_id (0=irrelevant,
                        1=male, 2=female, 3=non-binary}
  -f FROM_PAGE, --from FROM_PAGE
                        lower boundary of the search pages to scrape
                        (boundaries are included)
  -t TO_PAGE, --to TO_PAGE
                        upper boundary of the search pages to scrape
                        (boundaries are included)
  -db DB, --database DB
                        file path of the sqlite3 database
  -v, --verbose         display every scraped user object
```
