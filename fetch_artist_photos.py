"""Save the primary artist photo supplied by each public Ticketmaster artist page."""
import json,re
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.request import Request,urlopen
from concurrent.futures import ThreadPoolExecutor
from import_ticketmaster import ARTISTS,source_url
ROOT=Path(__file__).parent

def fetch_photo(slug):
 page=source_url(slug)
 html=urlopen(Request(page,headers={'User-Agent':'Mozilla/5.0'}),timeout=30).read().decode()
 match=re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',html,re.S)
 queries=json.loads(match[1])['props']['pageProps']['initialReduxState']['api']['queries']
 info=next(v['data'] for k,v in queries.items() if k==f'artistInfo("{ARTISTS[slug]["id"]}")')
 url=info['imageUrl']
 if not url.startswith('https://s1.ticketm.net/'):raise ValueError('Unexpected photo source')
 response=urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=30);data=response.read()
 if not data.startswith(b'\xff\xd8'):raise ValueError('Expected JPEG image')
 dest=ROOT/'public'/'artists'/(slug+'.jpg');dest.parent.mkdir(exist_ok=True);dest.write_bytes(data)
 print(slug, len(data),'bytes',flush=True)
 return slug,{'path':'/artists/'+slug+'.jpg','source_url':url,'source_page':page,'credit':'Artist photo via Ticketmaster','retrieved_at':datetime.now(ZoneInfo('America/New_York')).date().isoformat()}
if __name__=='__main__':
 with ThreadPoolExecutor(max_workers=3) as pool:photos=dict(pool.map(fetch_photo,ARTISTS))
 dest=ROOT/'artist-photos.json';dest.write_text(json.dumps(photos,indent=2))
