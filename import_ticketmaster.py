"""Read paginated public Ticketmaster artist pages into dated local snapshots."""
import json,re,math,argparse,hashlib,collections
from pathlib import Path
from urllib.request import Request,urlopen
from datetime import datetime
from zoneinfo import ZoneInfo
ROOT=Path(__file__).parent
ARTISTS={
 'olivia-rodrigo':{'name':'Olivia Rodrigo','id':'2836194','image':'violet'},
 'noah-kahan':{'name':'Noah Kahan','id':'2385568','image':'forest'},
 'sombr':{'name':'sombr','id':'3144534','image':'cobalt'},
 'phoebe-bridgers':{'name':'Phoebe Bridgers','id':'2133305','image':'ice'},
 'gracie-abrams':{'name':'Gracie Abrams','id':'2763148','image':'rose'},
 'charli-xcx':{'name':'Charli XCX','id':'1638380','image':'violet'},
}
if (ROOT/'additional-artists.json').exists():ARTISTS.update(json.loads((ROOT/'additional-artists.json').read_text()))
def source_url(slug):return f'https://www.ticketmaster.com/{slug}-tickets/artist/{ARTISTS[slug]["id"]}'
def page(number,slug='olivia-rodrigo'):
 url=source_url(slug)+'?global=true&page='+str(number)
 html=urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=30).read().decode()
 match=re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',html,re.S)
 if not match:raise ValueError('Ticketmaster page structure changed; previous snapshot kept.')
 queries=json.loads(match[1])['props']['pageProps']['initialReduxState']['api']['queries']
 for key,value in queries.items():
  if not key.startswith('artistEvents('):continue
  args=json.loads(key[len('artistEvents('):-1])
  if str(args.get('artistId'))==ARTISTS[slug]['id'] and args.get('page')==number and not args.get('startDate'):
   return value['data'],url
 raise ValueError('Expected event page not found; previous snapshot kept.')
def refresh(as_of=None,slug='olivia-rodrigo'):
 artist=ARTISTS[slug];first,url=page(0,slug);total=first['total'];events={};page_size=len(first['events'])
 if total and not page_size:raise ValueError('Source count has no events; previous snapshot kept.')
 pages=math.ceil(total/page_size) if total else 0
 for number in range(pages):
  data,source=(first,url) if number==0 else page(number,slug)
  if data['total']!=total:raise ValueError('Listing count changed mid-import; retry refresh.')
  for item in data['events']:
   start=item.get('dates',{}).get('startDate');zone=item.get('timeZone');local=datetime.fromisoformat(start.replace('Z','+00:00')).astimezone(ZoneInfo(zone)) if start and zone else None
   venue=item.get('venue',{});key=item['id'] if item['id']!='PARTNER' else 'partner-'+hashlib.sha256(item['url'].encode()).hexdigest()[:20]
   # Keep existing Olivia links. Other artists get independent communities even on shared festival bills.
   event_id='tm-'+('' if slug=='olivia-rodrigo' else slug+'-')+key
   title=item['title'];norm=lambda value:re.sub(r'[^a-z0-9]','',value.casefold());kind='tour' if norm(artist['name']) in norm(title) and not any(word in title.upper() for word in ('FESTIVAL','JINGLE BALL','CORONA CAPITAL','ROCK WERCHTER','PINKPOP','I-DAYS','SUMMER SESSIONS')) else 'appearance'
   events[key]={
    'id':event_id,'artist':artist['name'],'artist_slug':slug,'title':title,
    'venue':venue.get('name','Venue to be announced'),'city':venue.get('city','City to be announced'),
    'region':venue.get('state',''),'country':venue.get('countryCode',''),'start_date':local.date().isoformat() if local else '',
    'local_time':local.strftime('%H:%M') if local and not item.get('tba') else '', 'timezone':zone or '',
    'date':local.strftime('%B %d, %Y').replace(' 0',' ') if local else 'Date to be announced','image':artist['image'],
    'source':'Ticketmaster','source_url':item['url'],'listing_page':source,
    'status':'Cancelled' if item.get('cancelled') else 'Postponed' if item.get('postponed') else 'Rescheduled' if item.get('rescheduled') else 'Scheduled', 'kind':kind}
  print(slug+': page '+str(number+1)+'/'+str(pages),flush=True)
 if len(events)!=total:raise ValueError(f'Expected {total} unique listings, found {len(events)}; previous snapshot kept.')
 clean={};excluded=[]
 for event in sorted(events.values(),key=lambda e:e['id']):
  title=event['title'].upper()
  if any(word in title for word in ('PREMIUM PACKAGES','PRESTATION','PARKING','VIP PACKAGE','HOSPITALITY','COACH TRAVEL','HOTEL PACKAGE','VINYL ROOM','TICKET NOT INCLUDED','SHUTTLE','FAST TRACK','LEGAZY SEAT','BISTRONOMY','PREMIUM SEATS','AFTERPARTY','BANAMEX PLUS')):
   excluded.append({'id':event['id'],'reason':'Ancillary package, not an additional concert'});continue
  identity=(event['start_date'],event['local_time'],event['venue'].casefold(),event['city'].casefold(),event['country']) if event['start_date'] else (event['id'],)
  if identity in clean:
   clean[identity].setdefault('alternate_source_urls',[]).append(event['source_url']);excluded.append({'id':event['id'],'reason':'Duplicate listing for the same show'});continue
  clean[identity]=event
 # Some regional sources title tour concerts with just the artist's name.
 for event in clean.values():
  if event['title'].casefold()==artist['name'].casefold():event['kind']='tour'
 tours=collections.Counter(e['title'] for e in clean.values() if re.search(r'\btour\b',e['title'],re.I))
 label=tours.most_common(1)[0][0] if tours else 'Upcoming shows & appearances'
 label=re.sub('^'+re.escape(artist['name'])+r'\s*[:|–—-]?\s*','',label,flags=re.I) or 'Upcoming shows'
 snapshot={'artist':artist['name'],'slug':slug,'image':artist['image'],'tour_label':label,'source_url':source_url(slug),'imported_at':as_of or datetime.now(ZoneInfo('America/New_York')).date().isoformat(),'source_count':total,'excluded_listings':excluded,'events':sorted(clean.values(),key=lambda e:(e['start_date'] or '9999',e['id']))}
 dest=ROOT/'ticketmaster-events.json' if slug=='olivia-rodrigo' else ROOT/'imports'/(slug+'.json');dest.parent.mkdir(exist_ok=True);tmp=dest.with_suffix('.tmp');tmp.write_text(json.dumps(snapshot,indent=2));tmp.replace(dest)
 print(slug+': saved '+str(len(clean))+' distinct shows ('+str(total)+' source listings)',flush=True)
 return snapshot
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--as-of');parser.add_argument('--artist',choices=ARTISTS,default='olivia-rodrigo');parser.add_argument('--all',action='store_true');args=parser.parse_args()
 for slug in ARTISTS if args.all else [args.artist]:refresh(args.as_of,slug)
