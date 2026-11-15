"""Save venue coordinates from Ticketmaster artist listings without changing shows."""
import json,math,sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
from import_ticketmaster import ARTISTS,page
from server import venue_key
ROOT=Path(__file__).parent
DEST=ROOT/'venue-locations.json'
def collect(slug):
 first,url=page(0,slug);found={}
 for number in range(max(1,math.ceil(first.get('total',0)/20))):
  data,source=(first,url) if number==0 else page(number,slug)
  for e in data.get('events',[]):
   v=e.get('venue',{});lat=v.get('latitude');lon=v.get('longitude')
   if not isinstance(lat,(int,float)) or not isinstance(lon,(int,float)) or not math.isfinite(lat) or not math.isfinite(lon) or not -90<=lat<=90 or not -180<=lon<=180:continue
   venue={'venue':v.get('name',''),'city':v.get('city',''),'region':v.get('state',''),'country':v.get('countryCode','')}
   if not venue['venue'] or not venue['city']:continue
   found[venue_key(venue)]={**venue,'latitude':lat,'longitude':lon,'source_url':v.get('url') or source,'source':'Ticketmaster'}
 return slug,found
if __name__=='__main__':
 registry=json.loads(DEST.read_text()) if DEST.exists() else {}
 with ThreadPoolExecutor(max_workers=4) as pool:
  for task in as_completed([pool.submit(collect,s) for s in ARTISTS]):
   try:
    slug,data=task.result();registry.update(data);DEST.write_text(json.dumps(registry,indent=2));print(slug,len(data),flush=True)
   except Exception as e:print(type(e).__name__,str(e),flush=True)
 print('Saved',len(registry),'venue locations')
