"""Save Ticketmaster's own artist genre and subgenre classifications."""
import json,re
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.request import Request,urlopen
from concurrent.futures import ThreadPoolExecutor
from import_ticketmaster import ARTISTS,source_url
ROOT=Path(__file__).parent

def fetch_genres(slug):
 url=source_url(slug)
 html=urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=30).read().decode()
 match=re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',html,re.S)
 queries=json.loads(match[1])['props']['pageProps']['initialReduxState']['api']['queries']
 info=next(v['data'] for k,v in queries.items() if k==f'artistInfo("{ARTISTS[slug]["id"]}")')
 categories=[]
 for level,key in [('genre','minorCategory'),('subgenre','subMinorCategory')]:
  category=info.get(key) or {};name=category.get('name')
  if name and name.casefold() not in ('undefined','music') and name not in [c['name'] for c in categories]:categories.append({'id':category.get('id'),'name':name,'level':level})
 print(slug+': '+', '.join(c['name'] for c in categories),flush=True)
 return slug,{'categories':categories,'source_url':url,'retrieved_at':datetime.now(ZoneInfo('America/New_York')).date().isoformat()}
if __name__=='__main__':
 with ThreadPoolExecutor(max_workers=3) as pool:genres=dict(pool.map(fetch_genres,ARTISTS))
 (ROOT/'artist-genres.json').write_text(json.dumps(genres,indent=2))
