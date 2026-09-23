import requests

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'application/json',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://www.themuse.com/',
}
r = requests.get('https://www.themuse.com/api/public/jobs', params={'page': 1, 'descending': 'true'}, headers=headers, timeout=15)
print('Status:', r.status_code)
print('Jobs found:', len(r.json().get('results', [])) if r.ok else 'N/A')