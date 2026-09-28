import requests
from bs4 import BeautifulSoup
from scrapers.jobberman_scraper import JOB_LINK_RE

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml',
}
resp = requests.get('https://www.jobberman.com/jobs', headers=headers, timeout=15)
soup = BeautifulSoup(resp.text, 'html.parser')

title_links = soup.find_all('a', href=JOB_LINK_RE)
print(f"Found {len(title_links)} job title links\n")

tag = title_links[0]
print("TITLE TEXT:", repr(tag.get_text(strip=True)))

container = tag.find_parent(['div', 'li', 'article'])
print("\nCONTAINER TAG:", container.name if container else None)
print("CONTAINER CLASSES:", container.get('class') if container else None)

if container:
    strings = [s.strip() for s in container.stripped_strings if s.strip()]
    print(f"\nSTRIPPED STRINGS ({len(strings)} total):")
    for i, s in enumerate(strings):
        print(f"  [{i}] {s[:80]!r}")