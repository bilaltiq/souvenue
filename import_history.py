"""Import date/venue facts from public setlist.fm artist histories; never imports songs."""
import json,re,html,hashlib,unicodedata
from urllib.request import urlopen,Request
from urllib.parse import urljoin
from pathlib import Path
from datetime import date,datetime
from concurrent.futures import ThreadPoolExecutor,as_completed
from import_ticketmaster import ARTISTS
ROOT=Path(__file__).parent
from zoneinfo import ZoneInfo
TODAY=datetime.now(ZoneInfo('America/New_York')).date()
try:SINCE=TODAY.replace(year=TODAY.year-1)
except ValueError:SINCE=TODAY.replace(year=TODAY.year-1,day=28)
def clean(s):return html.unescape(re.sub('<[^>]+>','',s)).strip()
def norm(s):return re.sub('[^a-z0-9]','',unicodedata.normalize('NFKD',s).encode('ascii','ignore').decode().lower())
def fetch(url):
 for attempt in range(3):
  try:
   b=urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=20).read().decode()
   if 'setlistPreview' not in b:raise ValueError('No concert history markup returned')
   return b
  except Exception:
   if attempt==2:raise

def run(slug,url):
 records={};status='complete';pages=0;error=''
 try:
  for page in range(1,41):
   b=fetch(url+('?page='+str(page) if page>1 else ''));pages=page
   dates=[]
   blocks=b.split('<div class="col-xs-12 setlistPreview">')[1:]
   for block in blocks:
    def val(cls):
     m=re.search(r'<span class="'+cls+r'">(.*?)</span>',block,re.S);return clean(m[1]) if m else ''
    d=date.fromisoformat(datetime.strptime(val('month')+' '+val('day')+' '+val('year'),'%b %d %Y').date().isoformat());dates.append(d)
    if not SINCE<=d<=TODAY:continue
    artist=re.search(r'Artist:\s*<strong><a[^>]*>(.*?)</a>',block,re.S)
    if not artist or norm(clean(artist[1]))!=norm(ARTISTS[slug]['name']):continue
    venue=re.search(r'Venue:\s*<strong><a[^>]*>(.*?)</a>',block,re.S)
    link=re.search(r'<h2><a href="([^"]+)"',block)
    if not venue or not link:continue
    place=clean(venue[1]).rsplit(', ',3)
    if len(place)<3:continue
    if len(place)==4 and place[-1] in ['USA','Canada']:v,city,region,country=place
    else:
     parts=clean(venue[1]).rsplit(', ',2);v,city,country=parts;region=''
    key=norm(ARTISTS[slug]['name']+'|'+v+'|'+city+'|'+str(d));eid='past-'+hashlib.sha256(key.encode()).hexdigest()[:24]
    records[eid]={'id':eid,'artist':ARTISTS[slug]['name'],'artist_slug':slug,'venue':v,'city':city,'region':region,'country':country,'start_date':str(d),'date':d.strftime('%b %d, %Y'),'source':'setlist.fm','source_url':urljoin(url,link[1])}
   if dates and min(dates)<SINCE:break
   if not re.search(r'(?:[?&]|&amp;)page='+str(page+1)+r'(?:["&])',b):break
  else:status='partial';error='Page limit reached'
 except Exception as e:status='partial' if records else 'unavailable';error=str(e)
 return slug,{'source_url':url,'status':status,'error':error,'pages':pages,'events':sorted(records.values(),key=lambda x:x['start_date'],reverse=True)}
if __name__=='__main__':
 manifest=json.loads((ROOT/'past-events.json').read_text()) if (ROOT/'past-events.json').exists() else {'artists':{}}
 urls=[a['source_url'].split('?')[0] for a in manifest['artists'].values()];mapping={}
 for slug in ARTISTS:
  matches=[u for u in urls if re.search('/'+re.escape(slug)+r'-[0-9a-f]+\.html$',u)]
  if matches:mapping[slug]=matches[0]
 mapping['ed-sheeran']='https://www.setlist.fm/setlists/ed-sheeran-53d5f3bd.html'
 mapping['role-model']='https://www.setlist.fm/setlists/role-model-5bf0e748.html'
 output={'imported_at':str(TODAY),'since':str(SINCE),'until':str(TODAY),'artists':{}}
 with ThreadPoolExecutor(max_workers=4) as pool:
  for task in as_completed([pool.submit(run,s,u) for s,u in mapping.items()]):
   slug,data=task.result();output['artists'][slug]=data;print(slug,len(data['events']),data['status'],flush=True)
   (ROOT/'past-events.json').write_text(json.dumps(output,indent=2,ensure_ascii=False))
 print('ARTISTS',len(mapping),'EVENTS',sum(len(a['events']) for a in output['artists'].values()))
