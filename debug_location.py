# debug_location.py — dumps the raw string sequence for one job card
import scrapers.jobberman_scraper as js
import requests
from bs4 import BeautifulSoup

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
resp = requests.get('https://www.jobberman.com/jobs', headers=headers, timeout=15)
soup = BeautifulSoup(resp.text, 'html.parser')
tag = soup.find_all('a', href=js.JOB_LINK_RE)[0]

container = js.find_card_container(tag)
junk = {'FEATURED', 'Popular', 'Easy apply', tag.get_text(strip=True)}
strings = [s.strip() for s in container.stripped_strings if s.strip()]
strings = [s for s in strings if s not in junk and len(s) > 1]
for i, s in enumerate(strings):
    print(f"[{i}] {s!r}")