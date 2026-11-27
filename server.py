import os,json,sqlite3,secrets,hashlib,hmac,time,re,unicodedata,math,base64
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from urllib.parse import urlparse,unquote,parse_qs,quote
import urllib.request,urllib.error
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from functools import lru_cache
ATTENDANCE_POINTS=100
GPS_RADIUS_METERS=500
GPS_MAX_ACCURACY_METERS=100
def hosted():return bool(os.environ.get('VERCEL') or os.environ.get('DATABASE_URL'))
def demo_checkins_enabled():return not hosted() and os.environ.get("SOUVENUE_DEMO_CHECKINS","1")=="1"
MAX_PHOTO_BYTES=2_000_000 if hosted() else 25_000_000
MAX_POST_PHOTO_BYTES=2_800_000 if hosted() else 100_000_000
MAX_FEED_REQUEST_BYTES=4*((MAX_POST_PHOTO_BYTES+2)//3)+100_000
MAX_REQUEST_BYTES=4*((MAX_PHOTO_BYTES+2)//3)+100_000
def photo_bytes(photo):
 encoded=photo.partition(',')[2]
 return len(encoded)*3//4-(len(encoded)-len(encoded.rstrip('=')))
def photo_too_large(photo):return photo_bytes(photo)>MAX_PHOTO_BYTES

# ---- Photo metadata stripping --------------------------------------------
# Phone photos carry GPS coordinates and other EXIF data. The browser re-saves
# photos before upload (which drops all metadata); this is the server-side
# backup for anything that arrives with metadata anyway. Pixels are untouched.
def _strip_jpeg(raw):
 out=bytearray(raw[:2]);i=2
 while i+4<=len(raw):
  if raw[i]!=0xFF:return raw
  marker=raw[i+1]
  if marker==0xFF:i+=1;continue
  if marker==0xDA or marker==0xD9:out+=raw[i:];return bytes(out)
  if 0xD0<=marker<=0xD7 or marker==0x01:out+=raw[i:i+2];i+=2;continue
  size=int.from_bytes(raw[i+2:i+4],'big')
  if size<2 or i+2+size>len(raw):return raw
  if marker not in (0xE1,0xED,0xFE):out+=raw[i:i+2+size]   # drop APP1 (Exif/XMP), APP13 (IPTC), comments
  i+=2+size
 return raw
def _strip_png(raw):
 out=bytearray(raw[:8]);i=8
 while i+12<=len(raw):
  size=int.from_bytes(raw[i:i+4],'big');kind=raw[i+4:i+8];end=i+12+size
  if end>len(raw):return raw
  if kind not in (b'eXIf',b'tEXt',b'zTXt',b'iTXt',b'tIME'):out+=raw[i:end]
  i=end
 return bytes(out) if i==len(raw) else raw
def _strip_webp(raw):
 chunks=[];i=12
 while i+8<=len(raw):
  kind=raw[i:i+4];size=int.from_bytes(raw[i+4:i+8],'little');end=i+8+size+(size&1)
  if end>len(raw):return raw
  if kind not in (b'EXIF',b'XMP '):
   chunk=bytearray(raw[i:end])
   if kind==b'VP8X':chunk[8]&=~0x0C&0xFF   # clear the EXIF/XMP flags
   chunks.append(bytes(chunk))
  i=end
 body=b'WEBP'+b''.join(chunks)
 return b'RIFF'+len(body).to_bytes(4,'little')+body
def strip_photo_metadata(photo):
 if not isinstance(photo,str) or not photo.startswith('data:image/') or ',' not in photo:return photo
 head,b64=photo.split(',',1)
 try:raw=base64.b64decode(b64,validate=True)
 except Exception:return photo
 try:
  if raw[:2]==b'\xff\xd8':clean=_strip_jpeg(raw)
  elif raw[:8]==b'\x89PNG\r\n\x1a\n':clean=_strip_png(raw)
  elif raw[:4]==b'RIFF' and raw[8:12]==b'WEBP':clean=_strip_webp(raw)
  else:return photo
 except Exception:return photo
 return photo if clean==raw else head+','+base64.b64encode(clean).decode()
GENERAL_TOPICS={'lounge','meetups','merch','bst','box-office','questions','outfits','views','stories','travel','city-crowds'}
POST_TAGS=('Merch','BST','Box Office','Questions','Outfits','Views','Stories')
ROOT=Path(__file__).parent
DB=Path(os.environ.get('SOUVENUE_DB',str(ROOT/'demo.sqlite3')))
class LocalConnection(sqlite3.Connection):
 def __exit__(self,*args):
  try:return super().__exit__(*args)
  finally:self.close()

def db():
 url=os.environ.get('DATABASE_URL')
 if url:
  from database import PostgresConnection
  return PostgresConnection(url)
 if os.environ.get('VERCEL'):raise RuntimeError('DATABASE_URL is required on Vercel; local SQLite is not persistent.')
 c=sqlite3.connect(DB,factory=LocalConnection);c.row_factory=sqlite3.Row;return c

def password_digest(password,salt):
 raw_password=password.encode();raw_salt=salt.encode()
 if hasattr(hashlib,'scrypt'):
  return 'scrypt$'+hashlib.scrypt(raw_password,salt=raw_salt,n=16384,r=8,p=1).hex()
 rounds=310000
 digest=hashlib.pbkdf2_hmac('sha256',raw_password,raw_salt,rounds).hex()
 return f'pbkdf2_sha256${rounds}${digest}'

def password_matches(password,stored,salt):
 raw_password=password.encode();raw_salt=salt.encode()
 if stored.startswith('pbkdf2_sha256$'):
  try:
   _,rounds,digest=stored.split('$',2)
   candidate=hashlib.pbkdf2_hmac('sha256',raw_password,raw_salt,int(rounds)).hex()
   return hmac.compare_digest(digest,candidate)
  except (ValueError,TypeError):return False
 if stored.startswith('scrypt$'):
  if not hasattr(hashlib,'scrypt'):return False
  stored=stored.split('$',1)[1]
 if not hasattr(hashlib,'scrypt'):return False
 candidate=hashlib.scrypt(raw_password,salt=raw_salt,n=16384,r=8,p=1).hex()
 return hmac.compare_digest(stored,candidate)

def strip_stored_photo_metadata(c):
 """One-time pass: remove GPS/EXIF from photos uploaded before stripping existed."""
 c.execute('CREATE TABLE IF NOT EXISTS maintenance(name TEXT PRIMARY KEY)')
 if c.execute("SELECT 1 FROM maintenance WHERE name='strip-photo-metadata-v1'").fetchone():return
 for row in c.execute('SELECT id,photo,extra_photos FROM feed_posts').fetchall():
  photo=strip_photo_metadata(row['photo']);extra=json.dumps([strip_photo_metadata(x) for x in json.loads(row['extra_photos'] or '[]')])
  if photo!=row['photo'] or extra!=(row['extra_photos'] or '[]'):c.execute('UPDATE feed_posts SET photo=?,extra_photos=? WHERE id=?',(photo,extra,row['id']))
 for row in c.execute("SELECT id,photo FROM posts WHERE photo IS NOT NULL AND photo!=''").fetchall():
  photo=strip_photo_metadata(row['photo'])
  if photo!=row['photo']:c.execute('UPDATE posts SET photo=? WHERE id=?',(photo,row['id']))
 c.execute("INSERT INTO maintenance(name) VALUES('strip-photo-metadata-v1')")
# One-time account removals requested by the site owner, matched by id AND exact name.
REMOVED_ACCOUNTS=[('acf92cbf56a731b4e15824589250f137','Gob')]   # duplicate of "gob" that differs only by case (Nov 2026)
def remove_requested_accounts(c):
 c.execute('CREATE TABLE IF NOT EXISTS maintenance(name TEXT PRIMARY KEY)')
 for uid,name in REMOVED_ACCOUNTS:
  marker='remove-account-'+uid
  if c.execute('SELECT 1 FROM maintenance WHERE name=?',(marker,)).fetchone():continue
  if c.execute('SELECT 1 FROM users WHERE id=? AND name=?',(uid,name)).fetchone():
   for table in ('sessions','attendance','concert_logs','feed_posts','posts','thread_replies','threads','community_messages','community_members'):
    c.execute(f'DELETE FROM {table} WHERE user=?',(uid,))
   c.execute('DELETE FROM friendships WHERE low=? OR high=?',(uid,uid))
   c.execute('DELETE FROM users WHERE id=?',(uid,))
  c.execute('INSERT INTO maintenance(name) VALUES(?)',(marker,))
def initialize():
 with db() as c:
  if os.environ.get('DATABASE_URL'):
   c.execute('SELECT pg_advisory_xact_lock(73118541)')
   c.execute('CREATE SCHEMA IF NOT EXISTS souvenue')
  c.executescript('''CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,name TEXT UNIQUE,password TEXT,salt TEXT);CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user TEXT,expires REAL);CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY,artist TEXT,venue TEXT,city TEXT,date TEXT,image TEXT);CREATE TABLE IF NOT EXISTS attendance(user TEXT,event TEXT,created REAL,PRIMARY KEY(user,event));CREATE TABLE IF NOT EXISTS posts(id TEXT PRIMARY KEY,user TEXT,scope TEXT,body TEXT,photo TEXT,created REAL);''')
  if 'method' not in [r[1] for r in c.execute('PRAGMA table_info(attendance)')]:c.execute("ALTER TABLE attendance ADD COLUMN method TEXT NOT NULL DEFAULT 'demo'")
  if 'visibility' not in [r[1] for r in c.execute('PRAGMA table_info(users)')]:c.execute("ALTER TABLE users ADD COLUMN visibility TEXT NOT NULL DEFAULT 'public'")
  if 'leaderboard_opt_in' not in [r[1] for r in c.execute('PRAGMA table_info(users)')]:c.execute("ALTER TABLE users ADD COLUMN leaderboard_opt_in INTEGER NOT NULL DEFAULT 0")
  c.execute("CREATE TABLE IF NOT EXISTS concert_logs(id TEXT PRIMARY KEY,user TEXT,identity TEXT,event_id TEXT,artist TEXT,venue TEXT,city TEXT,date TEXT,created REAL,artists_seen TEXT DEFAULT 'null',UNIQUE(user,identity))")
  if 'artists_seen' not in [r[1] for r in c.execute('PRAGMA table_info(concert_logs)')]:c.execute("ALTER TABLE concert_logs ADD COLUMN artists_seen TEXT DEFAULT 'null'")
  if 'rating' not in [r[1] for r in c.execute('PRAGMA table_info(concert_logs)')]:c.execute("ALTER TABLE concert_logs ADD COLUMN rating REAL")
  c.execute("CREATE TABLE IF NOT EXISTS feed_posts(id TEXT PRIMARY KEY,user TEXT,body TEXT,photo TEXT,event_id TEXT,category TEXT,created REAL)")
  if 'extra_photos' not in [r[1] for r in c.execute('PRAGMA table_info(feed_posts)')]:c.execute("ALTER TABLE feed_posts ADD COLUMN extra_photos TEXT NOT NULL DEFAULT '[]'")
  if 'featured' not in [r[1] for r in c.execute('PRAGMA table_info(feed_posts)')]:c.execute("ALTER TABLE feed_posts ADD COLUMN featured INTEGER NOT NULL DEFAULT 0")
  c.execute('CREATE TABLE IF NOT EXISTS artist_profiles(slug TEXT PRIMARY KEY,data TEXT,fetched REAL)')
  strip_stored_photo_metadata(c)
  remove_requested_accounts(c)
  c.executescript("""CREATE TABLE IF NOT EXISTS friendships(low TEXT,high TEXT,sender TEXT,status TEXT,created REAL,PRIMARY KEY(low,high));
  CREATE TABLE IF NOT EXISTS communities(id TEXT PRIMARY KEY,name TEXT,description TEXT,topic TEXT,creator TEXT,starter INTEGER,created REAL);
  CREATE TABLE IF NOT EXISTS community_members(community TEXT,user TEXT,joined REAL,PRIMARY KEY(community,user));
  CREATE TABLE IF NOT EXISTS community_messages(id TEXT PRIMARY KEY,community TEXT,user TEXT,body TEXT,created REAL);""")
  if 'category' not in [r[1] for r in c.execute('PRAGMA table_info(communities)')]:
   c.execute("ALTER TABLE communities ADD COLUMN category TEXT NOT NULL DEFAULT 'general'")
   c.execute("UPDATE communities SET category='artists' WHERE topic='Artist fans'")
  c.executescript("CREATE TABLE IF NOT EXISTS threads(id TEXT PRIMARY KEY,scope TEXT,user TEXT,title TEXT,body TEXT,created REAL);CREATE TABLE IF NOT EXISTS thread_replies(id TEXT PRIMARY KEY,thread TEXT,user TEXT,body TEXT,created REAL);")
  if 'subcategory' not in [r[1] for r in c.execute('PRAGMA table_info(communities)')]:
   c.execute("ALTER TABLE communities ADD COLUMN subcategory TEXT NOT NULL DEFAULT 'lounge'")
   c.execute("UPDATE communities SET subcategory='city-crowds' WHERE topic='City'")
  starters=[('concert-crowd','The concert crowd','Find people who live for live music.','Concerts'),('new-york-crowd','New York nights','Meet the crowd around New York shows.','City'),('boston-crowd','Boston nights','Talk shows and meet concert fans around Boston.','City')]
  starters += [(slug+'-fans',name+' fans','An independent place for '+name+' fans to talk music and shows.','Artist fans') for slug,name in [('olivia-rodrigo','Olivia Rodrigo'),('noah-kahan','Noah Kahan'),('sombr','sombr'),('phoebe-bridgers','Phoebe Bridgers'),('gracie-abrams','Gracie Abrams'),('charli-xcx','Charli XCX')]]
  c.executemany('INSERT OR IGNORE INTO communities(id,name,description,topic,creator,starter,created) VALUES(?,?,?,?,?,?,?)',[(cid,name,desc,topic,None,1,0) for cid,name,desc,topic in starters])
  c.execute("UPDATE communities SET category='artists' WHERE starter=1 AND topic='Artist fans'")
  c.execute("UPDATE communities SET subcategory='city-crowds' WHERE starter=1 AND topic='City'")
  if 'category' not in [r[1] for r in c.execute('PRAGMA table_info(posts)')]:c.execute("ALTER TABLE posts ADD COLUMN category TEXT NOT NULL DEFAULT 'general'")
  if 'tags' not in [r[1] for r in c.execute('PRAGMA table_info(posts)')]:
   c.execute("ALTER TABLE posts ADD COLUMN tags TEXT NOT NULL DEFAULT '[]'")
   c.execute("UPDATE posts SET tags='[\"Merch\"]' WHERE category='merch'")
  if 'metadata' not in [r[1] for r in c.execute('PRAGMA table_info(events)')]:c.execute("ALTER TABLE events ADD COLUMN metadata TEXT NOT NULL DEFAULT '{}'")
  c.executemany('INSERT OR IGNORE INTO events(id,artist,venue,city,date,image) VALUES(?,?,?,?,?,?)', [('noah-kahan','Noah Kahan','Citi Field (unconfirmed)','New York','July 18 · year unconfirmed','forest'),('olivia-rodrigo','Olivia Rodrigo','Venue to confirm','Boston','October 18 · year unconfirmed','violet')])
  for snapshot in source_snapshots():
   # Refresh one artist without unlisting other artists' shows.
   c.execute("UPDATE events SET metadata=json_set(metadata,'$.listed',0) WHERE json_extract(metadata,'$.source')='Ticketmaster' AND json_extract(metadata,'$.artist_slug')=?",(snapshot['slug'],))
   for event in snapshot['events']:
    metadata={**event,'imported_at':snapshot['imported_at'],'listed':True}
    c.execute('INSERT INTO events(id,artist,venue,city,date,image,metadata) VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET artist=excluded.artist,venue=excluded.venue,city=excluded.city,date=excluded.date,image=excluded.image,metadata=excluded.metadata',(event['id'],event['artist'],event['venue'],event['city'],event['date'],event['image'],json.dumps(metadata)))
  seed_more_communities(c)

def seed_more_communities(c):
 def add(cid,name,description,category,subcategory='lounge'):
  c.execute('INSERT OR IGNORE INTO communities(id,name,description,topic,creator,starter,created,category,subcategory) VALUES(?,?,?,?,NULL,1,0,?,?)',(cid,name,description,category.title(),category,subcategory))
 for snapshot in source_snapshots():
  add(snapshot['slug']+'-fans',snapshot['artist']+' fans','An independent space for '+snapshot['artist']+' fans to talk music and shows.','artists')
  label=snapshot.get('tour_label','')
  if snapshot['events'] and label and not label.startswith('Upcoming'):
   add('tour-'+snapshot['slug'],snapshot['artist']+' · '+label,'Follow the tour across dates and cities. Share plans, favorite moments, and tour talk with other fans.','tours')
 venues={}
 for event in event_records(c):
  if event['source']!='Ticketmaster' or not event.get('listed'):continue
  group=venues.setdefault(event['venue_key'],{'event':event,'count':0});group['count']+=1
 for key,group in sorted(venues.items(),key=lambda pair:(-pair[1]['count'],pair[1]['event']['venue']))[:30]:
  event=group['event'];add('venue-'+key,event['venue']+' · '+event['city'],'Meet venue regulars and share entrances, transport, seating tips, and memories from '+event['venue']+'.','venues')
 topics=[('meetups','Concert buddies','Find people to share your next night out.'),('meetups','Going solo','Meet other solo concertgoers and make plans.'),('merch','Merch stand discoveries','Talk displays, designs, and concert keepsakes.'),('merch','Collectors corner','Share your favorite music and tour collectibles.'),('bst','Buy, sell & trade','Discuss swaps and connect with fellow fans.'),('bst','Trade wishlists','Share what you collect and what you would love to trade.'),('box-office','Box office talk','Compare box office experiences and ask ticket questions.'),('box-office','Last-minute plans','Talk day-of-show plans with the crowd.'),('questions','First concert questions','No question is too small when it is your first show.'),('questions','Ask the crowd','Get advice from people who love live music.'),('outfits','Concert outfit ideas','Share the look you are planning for your next show.'),('outfits','Make it yourself','Talk custom shirts, bracelets, and creative concert looks.'),('views','Seat views & sightlines','Compare the view from different sections.'),('views','Photo & camera tips','Swap tips for capturing your favorite moments.'),('stories','You had to be there','Tell the concert story you keep coming back to.'),('stories','Favorite live moments','Share the final song, surprise guest, or moment that stayed with you.'),('travel','Getting to the show','Talk transport, parking, and travel plans.'),('travel','Concert road trips','Plan nights out beyond your own city.'),('city-crowds','Local music discoveries','Share the local shows and scenes you love.')]
 for index,(subcategory,name,description) in enumerate(topics):add('general-'+subcategory+'-'+str(index),name,description,'general',subcategory)

def source_snapshots():
 paths=[ROOT/'ticketmaster-events.json',*sorted((ROOT/'imports').glob('*.json'))]
 return [json.loads(path.read_text(encoding='utf-8')) for path in paths if path.exists()]

# ---- Open-data artist profiles ---------------------------------------------
# Facts, official links and a freely licensed photo from MusicBrainz (CC0),
# Wikidata (CC0) and Wikimedia Commons (per-photo licence, credited). Fetched once per artist, cached, refreshed about monthly.
OPEN_DATA_UA='Souvenue/0.1 ( https://souvenue.com )'
PROFILE_TTL=30*86400
PROFILE_RETRY_TTL=86400
_musicbrainz_last=[0.0]
def open_get(url,musicbrainz=False,tries=3):
 for attempt in range(tries):
  if musicbrainz:  # MusicBrainz asks for at most one request per second
   wait=1.1-(time.time()-_musicbrainz_last[0])
   if wait>0:time.sleep(wait)
   _musicbrainz_last[0]=time.time()
  try:
   request=urllib.request.Request(url,headers={'User-Agent':OPEN_DATA_UA,'Accept':'application/json'})
   with urllib.request.urlopen(request,timeout=12) as response:return json.loads(response.read())
  except urllib.error.HTTPError as error:
   if error.code in (429,502,503,504) and attempt<tries-1:time.sleep(1.5*(attempt+1));continue
   if error.code==404:return None
   raise
  except (urllib.error.URLError,TimeoutError,OSError):  # slow or dropped connection: retry, then give up
   if attempt<tries-1:time.sleep(1.5*(attempt+1));continue
   raise
 return None
def _plain(text):return re.sub(r'\s+',' ',re.sub(r'<[^>]+>','',str(text or ''))).strip()
def _norm_name(value):return re.sub(r'[^a-z0-9]','',unicodedata.normalize('NFKD',str(value)).encode('ascii','ignore').decode().lower())
LINK_LABELS=[('instagram.com','Instagram'),('tiktok.com','TikTok'),('youtube.com','YouTube'),('open.spotify.com','Spotify'),('music.apple.com','Apple Music'),('bandcamp.com','Bandcamp'),('soundcloud.com','SoundCloud'),('twitter.com','X'),('x.com','X'),('facebook.com','Facebook')]
def fetch_artist_profile(name,mbid=None,photo=True):
 if not mbid:
  found=open_get('https://musicbrainz.org/ws/2/artist/?query='+quote(f'artist:"{name}"')+'&fmt=json&limit=5',musicbrainz=True) or {}
  candidates=[a for a in found.get('artists',[]) if a.get('score',0)>=90]
  exact=[a for a in candidates if _norm_name(a.get('name'))==_norm_name(name) or any(_norm_name(alias.get('name'))==_norm_name(name) for alias in a.get('aliases',[]))]
  pick=(exact or candidates or [None])[0]
  if not pick:return {'found':False}
  mbid=pick['id']
 artist=open_get(f'https://musicbrainz.org/ws/2/artist/{mbid}?inc=url-rels+artist-rels+genres&fmt=json',musicbrainz=True)
 if not artist:return {'found':False}
 name=artist.get('name',name)
 relations=artist.get('relations',[])
 links,seen,wikidata=[],set(),None
 for rel in relations:
  url=(rel.get('url') or {}).get('resource','')
  if not url or rel.get('ended'):continue
  if rel.get('type')=='wikidata':wikidata=url.rstrip('/').rsplit('/',1)[-1];continue
  label='Official site' if rel.get('type')=='official homepage' else next((l for d,l in LINK_LABELS if d in url),None)
  if label and label not in seen:seen.add(label);links.append({'label':label,'url':url})
 members=[rel['artist']['name'] for rel in relations if rel.get('type')=='member of band' and rel.get('direction')=='backward' and not rel.get('ended') and rel.get('artist')]
 genres=[g['name'] for g in sorted(artist.get('genres',[]),key=lambda g:-g.get('count',0))][:4]
 profile={'found':True,'mbid':mbid,'name':artist.get('name',name),'type':artist.get('type'),
  'origin':(artist.get('begin-area') or artist.get('area') or {}).get('name'),'country':artist.get('country'),
  'active_since':((artist.get('life-span') or {}).get('begin') or '')[:4] or None if artist.get('type')=='Group' else None,
  'members':list(dict.fromkeys(members))[:8],'genres':genres,'links':links[:8],'photo':None,
  'sources':{'musicbrainz':f'https://musicbrainz.org/artist/{mbid}'}}
 if wikidata:
  entity=((open_get(f'https://www.wikidata.org/wiki/Special:EntityData/{wikidata}.json') or {}).get('entities') or {}).get(wikidata) or {}
  profile['sources']['wikidata']=f'https://www.wikidata.org/wiki/{wikidata}'
  image=next((claim['mainsnak']['datavalue']['value'] for claim in (entity.get('claims') or {}).get('P18',[]) if claim.get('mainsnak',{}).get('datavalue')),None)
  if image and photo:
   info=open_get('https://commons.wikimedia.org/w/api.php?action=query&format=json&prop=imageinfo&iiprop=url|extmetadata&iiurlwidth=900&titles='+quote('File:'+image,safe=''))
   page=next(iter(((info or {}).get('query') or {}).get('pages',{}).values()),{})
   meta=(page.get('imageinfo') or [{}])[0]
   ext=meta.get('extmetadata') or {}
   licence=_plain((ext.get('LicenseShortName') or {}).get('value'))
   if meta.get('thumburl') and licence and 'non-free' not in licence.lower():
    profile['photo']={'url':meta['thumburl'],'page':meta.get('descriptionurl'),'author':_plain((ext.get('Artist') or {}).get('value'))[:120] or 'Wikimedia Commons','license':licence,'license_url':_plain((ext.get('LicenseUrl') or {}).get('value')) or None}
 return profile
def artist_profile(c,slug,name,mbid=None):  # mbid given: a searched artist (no photo lookup)
 row=c.execute('SELECT data,fetched FROM artist_profiles WHERE slug=?',(slug,)).fetchone()
 if row:
  data=json.loads(row['data']);age=time.time()-row['fetched']
  if age<(PROFILE_TTL if data.get('found') else PROFILE_RETRY_TTL):return data
 try:data=fetch_artist_profile(name,mbid,photo=not mbid)
 except Exception:
  if row:return json.loads(row['data'])
  return {'found':False,'unavailable':True}  # a failed lookup is not cached as "not found"
 data['fetched_at']=int(time.time())
 c.execute('DELETE FROM artist_profiles WHERE slug=?',(slug,))
 c.execute('INSERT INTO artist_profiles(slug,data,fetched) VALUES(?,?,?)',(slug,json.dumps(data),time.time() if data.get('found') else time.time()))
 return data

# ---- Search any artist ------------------------------------------------------
# The artists page lists a curated set; the search box also suggests any artist in
# MusicBrainz (about 2 million). Searched artists are not added to the list: they get
# a page at /artist/mb/<id> with open-data details and the shows fans have logged.
MBID_RE=re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
_artist_search_cache={}
_listens_this_year={}
def listen_post(url,payload):
 request=urllib.request.Request(url,data=json.dumps(payload).encode(),headers={'User-Agent':OPEN_DATA_UA,'Accept':'application/json','Content-Type':'application/json'})
 with urllib.request.urlopen(request,timeout=8) as response:return json.loads(response.read())
def listens_this_year(mbid):
 hit=_listens_this_year.get(mbid)
 if hit and time.time()-hit[0]<86400:return hit[1]
 try:data=(open_get(f'https://api.listenbrainz.org/1/stats/artist/{mbid}/listeners?range=this_year',tries=1) or {}).get('payload') or {}
 except Exception:return None
 count=data.get('total_listen_count') or 0
 if len(_listens_this_year)>20000:_listens_this_year.clear()
 _listens_this_year[mbid]=(time.time(),count)
 return count
def search_artists(query):
 query=re.sub(r'\s+',' ',str(query or '')).strip()[:80]
 words=[re.sub(r'([+\-!(){}\[\]^"~*?:\\/&|])',r'\\\1',w) for w in query.split(' ') if w]
 if len(query)<2 or not words:return []
 key=query.casefold();hit=_artist_search_cache.get(key)
 if hit and time.time()-hit[0]<86400:return hit[1]
 phrase=' '.join(words)
 lucene=f'artist:"{phrase}"^4 OR alias:"{phrase}"^2 OR ('+' AND '.join(f'artist:{w}' for w in words[:-1])+(' AND ' if words[:-1] else '')+f'artist:{words[-1]}*)'
 found=open_get('https://musicbrainz.org/ws/2/artist/?query='+quote(lucene)+'&fmt=json&limit=50',musicbrainz=True) or {}
 typed=[_norm_name(w) for w in query.split(' ') if _norm_name(w)]
 def matches(a):  # every typed word appears in the name or an alias (drops fuzzy look-alikes)
  names=[_norm_name(a.get('name'))]+[_norm_name(x.get('name')) for x in a.get('aliases') or []]
  return a.get('score',0)==100 or any(all(w in n for w in typed) for n in names)
 people=[a for a in found.get('artists',[]) if a.get('score',0)>=50 and a.get('type') not in ('Character','Choir','Orchestra') and matches(a)]
 # Popularity from ListenBrainz (MetaBrainz's open listening data): all-time listens for every
 # match, then this year's listens for the leaders, so current artists beat old ones.
 popularity={}
 try:popularity={p['artist_mbid']:p.get('total_listen_count') or 0 for p in listen_post('https://api.listenbrainz.org/1/popularity/artist',{'artist_mbids':[a['id'] for a in people]}) or []}
 except Exception:pass
 if popularity:
  leaders=sorted(people,key=lambda a:-popularity.get(a['id'],0))[:10]
  with ThreadPoolExecutor(max_workers=10) as pool:recent=dict(zip([a['id'] for a in leaders],pool.map(listens_this_year,[a['id'] for a in leaders])))
  score=lambda a:2*math.log10(1+(recent.get(a['id']) or 0))+math.log10(1+popularity.get(a['id'],0))
  people.sort(key=lambda a:(-score(a),-a.get('score',0)))
 else:
  people.sort(key=lambda a:(-(a.get('score',0)>=95),-min(len(a.get('tags') or []),12),-a.get('score',0)))
 results=[{'mbid':a['id'],'name':a.get('name',''),'disambiguation':a.get('disambiguation',''),'country':a.get('country',''),'type':a.get('type','')} for a in people[:8]]
 if len(_artist_search_cache)>2000:_artist_search_cache.clear()
 _artist_search_cache[key]=(time.time(),results)
 return results
def fan_logged_shows(c,name):
 target=artist_identity(name);shows={}
 for log in rows(c,'SELECT artist,venue,city,date,artists_seen FROM concert_logs'):
  try:seen=json.loads(log.get('artists_seen') or 'null') or []
  except (TypeError,ValueError):seen=[]
  if artist_identity(log['artist'])!=target and not any(artist_identity(x.get('artist',''))==target for x in seen if isinstance(x,dict)):continue
  key=concert_identity(log['artist'],log['venue'],log['city'],log['date'])
  show=shows.setdefault(key,{'headliner':log['artist'],'venue':log['venue'],'city':log['city'],'date':log['date'],'fans':0});show['fans']+=1
 return sorted(shows.values(),key=lambda x:x['date'],reverse=True)[:100]

# ---- Artist photo picker (local Demo studio only) ---------------------------
# Candidates come from the artist's Wikimedia Commons category and Openverse,
# limited to licences that allow any use. A chosen photo is downloaded, resized
# with macOS `sips`, saved to public/artists/<slug>.jpg, and credited in
# artist-photo-choices.json; both ship with the site.
PHOTO_CHOICES=ROOT/'artist-photo-choices.json'
FREE_LICENSES=('cc0','public domain','pdm','cc by','cc-by','by','by-sa')
def photo_choices():
 try:return json.loads(PHOTO_CHOICES.read_text(encoding='utf-8'))
 except (OSError,ValueError):return {}
def _free_license(name):
 n=(name or '').lower().replace('-',' ').strip()
 if not n or 'nc' in n.split() or 'nd' in n.split() or 'non commercial' in n or 'noncommercial' in n or 'no derivatives' in n:return False
 return n.startswith(('cc0','public domain','pdm','cc by','by'))
NOT_A_PHOTO=re.compile(r'logo|logotipo|signature|firma|\bsig\b|cover|album|poster|flag|\bmap\b|tracklist|screenshot|ticket',re.I)
def _commons_files(params):
 data=open_get('https://commons.wikimedia.org/w/api.php?action=query&format=json&prop=imageinfo&iiprop=url|size|mime|extmetadata&iiurlwidth=640&'+params) or {}
 return ((data.get('query') or {}).get('pages') or {}).values()
def photo_candidates(name,profile):
 out,seen=[],set()
 def key(url):return unquote(url.rsplit('/',1)[-1]).lower().replace(' ','_')
 def add(c):
  if re.search(r'getty|associated press|\breuters\b|\bafp\b',c.get('author') or '',re.I):return  # agency photos are often mislabelled uploads
  keys={key(c['url']),re.sub(r'^\d+px-','',key(c['url'])),_norm_name(re.sub(r'\.(jpe?g|png)$','',c['title'] or '',flags=re.I))}
  if keys&seen or NOT_A_PHOTO.search(c['title'] or ''):return
  seen.update(keys);out.append(c)
 def from_commons(page,pinned=False):
  info=(page.get('imageinfo') or [{}])[0];ext=info.get('extmetadata') or {}
  licence=_plain((ext.get('LicenseShortName') or {}).get('value'))
  if info.get('mime')!='image/jpeg' or min(info.get('width',0),info.get('height',0))<600 or not _free_license(licence):return
  add({'source':'Wikimedia Commons','thumb':info.get('thumburl') or info['url'],'url':info['url'],'page':info.get('descriptionurl'),'title':page.get('title','').replace('File:',''),'pinned':pinned,
   'author':_plain((ext.get('Artist') or {}).get('value'))[:120] or 'Wikimedia Commons','license':licence,'license_url':_plain((ext.get('LicenseUrl') or {}).get('value')) or None,'width':info.get('width'),'height':info.get('height')})
 qid=((profile or {}).get('sources') or {}).get('wikidata','').rstrip('/').rsplit('/',1)[-1]
 claims={}
 if qid:claims=((((open_get(f'https://www.wikidata.org/wiki/Special:EntityData/{qid}.json') or {}).get('entities') or {}).get(qid) or {}).get('claims') or {})
 value=lambda prop:next((c['mainsnak']['datavalue']['value'] for c in claims.get(prop,[]) if c.get('mainsnak',{}).get('datavalue')),None)
 main,category=value('P18'),value('P373')
 if main:
  for page in _commons_files('titles='+quote('File:'+main,safe='')):from_commons(page,pinned=True)
 categories=['Category:'+category] if category else []
 if category:
  subs=open_get('https://commons.wikimedia.org/w/api.php?action=query&format=json&list=categorymembers&cmtype=subcat&cmlimit=20&cmtitle='+quote('Category:'+category,safe='')) or {}
  categories+=[m['title'] for m in ((subs.get('query') or {}).get('categorymembers') or [])][:8]
 for cat in categories:
  for page in _commons_files('generator=categorymembers&gcmtype=file&gcmlimit=50&gcmtitle='+quote(cat,safe='')):from_commons(page)
 # Commons full-text search finds photos filed outside the artist's category.
 for page in _commons_files('generator=search&gsrnamespace=6&gsrlimit=30&gsrsearch='+quote(f'"{name}" filetype:bitmap')):
  if _norm_name(name) in _norm_name(page.get('title','')):from_commons(page)
 try:data=open_get('https://api.openverse.org/v1/images/?license_type=commercial&page_size=20&q='+quote(name)) or {}  # anonymous limit: 20 per page
 except Exception:data={}  # Openverse is optional
 for r in data.get('results',[]):
  if _norm_name(name) not in _norm_name(r.get('title','')) or not str(r.get('url','')).lower().endswith(('.jpg','.jpeg')):continue
  licence=f"CC {r.get('license','').upper()} {r.get('license_version','')}".replace('CC CC0','CC0').replace('CC PDM','Public domain').strip()
  if not _free_license(licence) or min(r.get('width') or 0,r.get('height') or 0)<600:continue
  add({'source':'Flickr' if r.get('source')=='flickr' else 'Wikimedia Commons' if r.get('source')=='wikimedia' else (r.get('source') or 'Openverse').title(),
   'thumb':r.get('thumbnail') or r.get('url'),'url':r.get('url'),'page':r.get('foreign_landing_url'),'title':r.get('title',''),'pinned':False,
   'author':(r.get('creator') or 'Unknown')[:120],'license':licence,'license_url':r.get('license_url'),'width':r.get('width'),'height':r.get('height')})
 # The main Wikidata photo first, then portrait-ish and larger photos (they crop best).
 out.sort(key=lambda c:(-int(c['pinned']),-(1 if 0.55<=(c['width'] or 1)/(c['height'] or 1)<=1.1 else 0),-((c['width'] or 0)*(c['height'] or 0))))
 return out[:24]
def save_photo_choice(slug,choice):
 import subprocess,tempfile
 url=str(choice.get('url',''))
 if not url.startswith('https://'):raise ValueError('Choose a photo from the list.')
 request=urllib.request.Request(url,headers={'User-Agent':OPEN_DATA_UA})
 with urllib.request.urlopen(request,timeout=30) as response:
  if not (response.headers.get('Content-Type') or '').startswith('image/'):raise ValueError('That link is not an image.')
  raw=response.read(30_000_000)
 target=ROOT/'public'/'artists'/f'{slug}.jpg'
 with tempfile.TemporaryDirectory() as tmp:
  src=Path(tmp)/'src';src.write_bytes(raw);out=Path(tmp)/'out.jpg'
  subprocess.run(['sips','-s','format','jpeg','-s','formatOptions','82','-Z','1200',str(src),'--out',str(out)],check=True,capture_output=True)
  target.write_bytes(out.read_bytes())
 choices=photo_choices()
 choices[slug]={'path':f'/artists/{slug}.jpg?v={int(time.time())}','source':choice.get('source'),'page':choice.get('page'),'author':choice.get('author'),'license':choice.get('license'),'license_url':choice.get('license_url'),'chosen':time.strftime('%Y-%m-%d')}
 PHOTO_CHOICES.write_text(json.dumps(choices,indent=1,ensure_ascii=False)+'\n',encoding='utf-8')
 return choices[slug]
def artist_records(c):
 photo_file=ROOT/'artist-photos.json';photos=json.loads(photo_file.read_text(encoding='utf-8')) if photo_file.exists() else {}
 genre_file=ROOT/'artist-genres.json';genres=json.loads(genre_file.read_text(encoding='utf-8')) if genre_file.exists() else {}
 catalog={s['slug']:{'artist_slug':s['slug'],'id':s['slug'],'artist':s['artist'],'source':'Ticketmaster','source_url':s['source_url'],'imported_at':s['imported_at'],'image':s.get('image','violet'),'tour_label':s.get('tour_label','Upcoming shows & appearances')} for s in source_snapshots()}
 for event in event_records(c):
  if event['artist_slug'] not in catalog:catalog[event['artist_slug']]=event
 choices=photo_choices()
 marks_file=ROOT/'artist-marks.json';marks=set(json.loads(marks_file.read_text(encoding='utf-8'))) if marks_file.exists() else set()  # drawn by scripts/crayon_marks.py
 for slug,artist in catalog.items():
  mark=slug in marks
  photo=None if mark else choices.get(slug)  # crayon marks replace photos; otherwise only photos picked in the studio: freely licensed and credited (no Ticketmaster images)
  artist['artist_photo']=photo['path'] if photo else ''
  artist['photo_credit']={k:photo.get(k) for k in ('author','license','license_url','page')} if photo else None
  artist['artist_mark']=f'/marks/{slug}.svg' if mark else ''  # crayon symbol, drawn by scripts/crayon_marks.py
  artist['genres']=[category['name'] for category in genres.get(slug,{}).get('categories',[])]
 return list(catalog.values())

def venue_key(event):
 def normalized(value):return re.sub(r'[^a-z0-9]','',unicodedata.normalize('NFKD',str(value)).encode('ascii','ignore').decode().casefold())
 name=normalized(event['venue'])
 if not name or any(word in name for word in ('unconfirmed','toconfirm','tobeannounced')):return 'unconfirmed-'+event['id']
 identity='|'.join(normalized(event.get(field,'')) for field in ('venue','city','region','country'))
 return hashlib.sha256(identity.encode()).hexdigest()[:32]

@lru_cache(maxsize=1)
def read_venue_locations(version):
 return json.loads((ROOT/'venue-locations.json').read_text(encoding='utf-8'))
def venue_locations():
 path=ROOT/'venue-locations.json'
 return read_venue_locations(path.stat().st_mtime_ns) if path.exists() else {}
def gps_policy(event,now=None):
 now=time.time() if now is None else now
 policy={'configured':False,'available':False,'radius_m':GPS_RADIUS_METERS,'max_accuracy_m':GPS_MAX_ACCURACY_METERS}
 location=venue_locations().get(event.get('venue_key') or venue_key(event))
 if not location:return {**policy,'reason':'Location check-in is not set up for this venue yet.'}
 try:
  zone=ZoneInfo(event['timezone']);day=datetime.strptime(event['start_date'],'%Y-%m-%d')
  if event.get('local_time'):
   start=datetime.combine(day.date(),datetime.strptime(event['local_time'],'%H:%M').time(),zone);opens=start-timedelta(hours=4);closes=start+timedelta(hours=8)
  else:
   opens=day.replace(hour=6,tzinfo=zone);closes=opens+timedelta(days=1)
 except (KeyError,ValueError,TypeError):return {**policy,'reason':'This show needs a confirmed date and venue time zone before location check-in opens.'}
 if event.get('status') in ('Cancelled','Postponed'):return {**policy,'reason':'Location check-in is unavailable for cancelled or postponed shows.'}
 policy.update(configured=True,latitude=location['latitude'],longitude=location['longitude'],opens_at=opens.isoformat(),closes_at=closes.isoformat())
 if now<opens.timestamp():return {**policy,'reason':'Location check-in opens closer to showtime.'}
 if now>closes.timestamp():return {**policy,'reason':'Location check-in has closed. You can still log this concert manually.'}
 return {**policy,'available':True,'reason':'Location check-in is open. Be within 500 metres of the venue.'}
def distance_meters(lat,lon,venue_lat,venue_lon):
 a,b=math.radians(lat),math.radians(venue_lat);dlat=b-a;dlon=math.radians(venue_lon-lon)
 h=math.sin(dlat/2)**2+math.cos(a)*math.cos(b)*math.sin(dlon/2)**2
 return 6371000*2*math.asin(math.sqrt(min(1,max(0,h))))
def validate_gps(event,data,now=None):
 now=time.time() if now is None else now;policy=gps_policy(event,now)
 if not policy['available']:return policy['reason']
 fields=[data.get(k) for k in ('latitude','longitude','accuracy','timestamp')]
 if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in fields):return 'A fresh, accurate device location is required. Try again.'
 lat,lon,accuracy,timestamp=fields
 if not -90<=lat<=90 or not -180<=lon<=180 or accuracy<=0:return 'The device returned an invalid location. Try again.'
 if not -5<=now-timestamp/1000<=60:return 'That location reading expired. Try checking in again.'
 if accuracy>GPS_MAX_ACCURACY_METERS:return 'Your location is too approximate. Enable precise location, move outdoors, and try again.'
 distance=distance_meters(lat,lon,policy['latitude'],policy['longitude'])
 if distance+accuracy>GPS_RADIUS_METERS:return 'You need to be closer to the venue to check in. Move within 500 metres and try again.'
 return None

def event_records(c):
 result=[]
 for r in rows(c,'SELECT * FROM events'):
  metadata=json.loads(r.pop('metadata'))
  event={'source':'Demo','artist_slug':r['id'],**r,**metadata};event['venue_key']=venue_key(event);policy=gps_policy(event);event['gps_checkin']={k:v for k,v in policy.items() if k not in ('latitude','longitude')};result.append(event)
 return result

def rows(c,q,args=()):return [dict(x) for x in c.execute(q,args)]
def can_view_profile(c,owner,viewer):
 row=c.execute('SELECT visibility FROM users WHERE id=?',(owner,)).fetchone()
 if not row:return False
 if row['visibility']=='public' or owner==viewer:return True
 return bool(viewer and c.execute("SELECT 1 FROM friendships WHERE status='accepted' AND ((low=? AND high=?) OR (low=? AND high=?))",(owner,viewer,viewer,owner)).fetchone())
def feed_records(c,where='',args=(),viewer=''):
 privacy="(users.visibility='public' OR users.id=? OR EXISTS(SELECT 1 FROM friendships WHERE status='accepted' AND ((low=users.id AND high=?) OR (high=users.id AND low=?))))"
 where+=(" AND " if where else " WHERE ")+privacy
 records=rows(c,"""SELECT feed_posts.*,users.name,events.artist,events.venue,events.city,events.date,
 EXISTS(SELECT 1 FROM attendance WHERE attendance.user=feed_posts.user AND attendance.event=feed_posts.event_id) AS attended
 FROM feed_posts JOIN users ON users.id=feed_posts.user LEFT JOIN events ON events.id=feed_posts.event_id """+where+' ORDER BY feed_posts.created DESC,feed_posts.id DESC LIMIT 50',(*args,viewer,viewer,viewer))
 for post in records:
  post['photos']=[post['photo'],*json.loads(post.pop('extra_photos'))]
  if hosted():
   post['photos']=['/api/media/feed/'+post['id']+'/'+str(i) for i in range(len(post['photos']))]
   post['photo']=post['photos'][0]
 return records

def historical_catalog():
 path=ROOT/'past-events.json'
 return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'artists':{}}
def concert_identity(artist,venue,city,date):
 def norm(value):return re.sub(r'[^a-z0-9]','',unicodedata.normalize('NFKD',str(value)).encode('ascii','ignore').decode().lower())
 return '|'.join(norm(x) for x in (artist,venue,city,date))
def artist_identity(artist):
 return re.sub(r'[^a-z0-9]','',unicodedata.normalize('NFKD',str(artist)).encode('ascii','ignore').decode().lower())
def logged_artist_count(history):
 return len({artist_identity(person.get('artist','')) for log in history for person in log.get('artists_seen',[]) if person.get('artist')})
def concert_history(c,uid):
 if not uid:return []
 history={}
 for log in rows(c,'SELECT * FROM concert_logs WHERE user=? ORDER BY created',(uid,)):
  try:seen=json.loads(log.get('artists_seen')) if log.get('artists_seen') is not None else None
  except (TypeError,ValueError):seen=None
  if seen is None:seen=[{'artist':log['artist'],'artist_slug':''}]
  history[log['identity']]={**log,'artists_seen':seen,'checked_in':False,'points':0,'start_date':log['date']}
 events={e['id']:e for e in event_records(c)}
 for attendance in rows(c,'SELECT * FROM attendance WHERE user=?',(uid,)):
  e=events.get(attendance['event'])
  if not e:continue
  day=e.get('start_date') or e['date'];key=concert_identity(e['artist'],e['venue'],e['city'],day)
  prior=next((log for log in history.values() if log.get('event_id')==e['id'] or concert_identity(log.get('artist',''),log.get('venue',''),log.get('city',''),log.get('start_date',''))==key),None)
  # An explicitly selected event always upgrades the same manual entry.
  for k,log in list(history.items()):
   if log.get('event_id')==e['id']:del history[k]
  seen=prior.get('artists_seen') if prior else [{'artist':e['artist'],'artist_slug':e.get('artist_slug','')}]
  history[key]={**e,**({'artists_seen':seen,'rating':prior.get('rating')} if prior else {}),'id':'checkin-'+e['id'],'event_id':e['id'],'checked_in':True,'checkin_method':attendance['method'],'points':ATTENDANCE_POINTS,'created':attendance['created'],'start_date':day}
 return sorted(history.values(),key=lambda e:(e['start_date'],e['created']),reverse=True)

class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def reply(self,status,data):
  b=json.dumps(data).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
 def user(self,c):
  token=next((v.strip()[8:] for v in self.headers.get('Cookie','').split(';') if v.strip().startswith('session=')), '')
  r=c.execute('SELECT users.id,users.name,users.visibility,users.leaderboard_opt_in FROM sessions JOIN users ON users.id=sessions.user WHERE token=? AND expires>?',(token,time.time())).fetchone();return dict(r) if r else None
 def do_GET(self):
  p=urlparse(self.path).path
  if hosted() and p=='/studio':return self.reply(404,{'error':'Not found'})
  if p.startswith('/api/'):
   with db() as c:
    u=self.user(c)
    if p.startswith('/api/media/'):
     parts=p.split('/')
     photo=None
     if len(parts)==6 and parts[3]=='feed' and parts[5].isdigit():
      record=c.execute('SELECT * FROM feed_posts WHERE id=?',(parts[4],)).fetchone()
      if record and can_view_profile(c,record['user'],u['id'] if u else ''):
       photos=[record['photo'],*json.loads(record['extra_photos'])];index=int(parts[5])
       if index<len(photos):photo=photos[index]
     elif len(parts)==5 and parts[3]=='post':
      record=c.execute('SELECT * FROM posts WHERE id=?',(parts[4],)).fetchone()
      if record and self.allowed(c,u,record['scope']):photo=record['photo']
     if not photo:return self.reply(404,{'error':'Photo unavailable.'})
     try:
      mime=photo.split(';',1)[0].removeprefix('data:');content=base64.b64decode(photo.partition(',')[2],validate=True)
     except (ValueError,TypeError):return self.reply(404,{'error':'Photo unavailable.'})
     if mime not in ('image/jpeg','image/png','image/webp'):return self.reply(404,{'error':'Photo unavailable.'})
     self.send_response(200);self.send_header('Content-Type',mime);self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Content-Length',str(len(content)));self.end_headers();self.wfile.write(content);return
    if p=='/api/past-events':return self.reply(200,historical_catalog())
    if p=='/api/state':return self.reply(200,{'demo_checkins_enabled':demo_checkins_enabled(),'hosted':hosted(),'max_photo_bytes':MAX_PHOTO_BYTES,'max_post_photo_bytes':MAX_POST_PHOTO_BYTES,'concert_history':concert_history(c,u['id']) if u else [],'artists_seen_count':logged_artist_count(concert_history(c,u['id'])) if u else 0,'user':u,'today':datetime.now(ZoneInfo('America/New_York')).date().isoformat(),'events':event_records(c),'artists':artist_records(c),'points':c.execute('SELECT COUNT(*) FROM attendance WHERE user=?',(u['id'],)).fetchone()[0]*ATTENDANCE_POINTS if u else 0,'points_per_checkin':ATTENDANCE_POINTS,'attendance':rows(c,'SELECT event,created,method,100 AS points FROM attendance WHERE user=? ORDER BY created DESC',(u['id'],)) if u else []})
    if p=='/api/leaderboards':
     options=parse_qs(urlparse(self.path).query);period=options.get('period',['all'])[0];scope=options.get('scope',['all'])[0]
     if period not in ('all','month') or scope not in ('all','friends'):return self.reply(400,{'error':'Choose a valid leaderboard filter.'})
     if scope=='friends' and not u:return self.reply(401,{'error':'Sign in to see your friends leaderboard.'})
     now=datetime.now(ZoneInfo('America/New_York'));cutoff=now.replace(day=1,hour=0,minute=0,second=0,microsecond=0).timestamp() if period=='month' else 0
     board=rows(c,'SELECT users.id,users.name,COUNT(attendance.event) AS concerts FROM users JOIN attendance ON attendance.user=users.id WHERE users.leaderboard_opt_in=1 AND attendance.created>=? GROUP BY users.id ORDER BY concerts DESC,users.name COLLATE NOCASE,users.id',(cutoff,))
     if scope=='friends':
      friends={r['low'] if r['high']==u['id'] else r['high'] for r in rows(c,"SELECT low,high FROM friendships WHERE status='accepted' AND (low=? OR high=?)",(u['id'],u['id']))};friends.add(u['id']);board=[row for row in board if row['id'] in friends]
     previous=None;rank=0
     for index,row in enumerate(board):
      if row['concerts']!=previous:rank=index+1
      previous=row['concerts'];row['rank']=rank;row['points']=row['concerts']*ATTENDANCE_POINTS
     mine=next((row for row in board if u and row['id']==u['id']),None)
     # Podium: each of the top three gets their latest photo the viewer is allowed to see.
     for row in board[:3]:
      latest=feed_records(c,'WHERE feed_posts.user=?',(row['id'],),viewer=u['id'] if u else '')
      row['photo']=latest[0]['photo'] if latest else None
     return self.reply(200,{'entries':board[:100],'participants':len(board),'mine':mine,'period':period,'scope':scope,'points_per_checkin':ATTENDANCE_POINTS})
    if p.startswith('/api/threads/'):
     scope=unquote(p[len('/api/threads/'):])
     if not self.readable(c,u,scope):return self.reply(403,{'error':'This chat is not available to your account.'})
     return self.reply(200,rows(c,'SELECT threads.*,users.name,(SELECT COUNT(*) FROM thread_replies WHERE thread=threads.id) AS replies FROM threads JOIN users ON users.id=threads.user WHERE scope=? ORDER BY created DESC',(scope,)))
    if p.startswith('/api/thread/'):
     tid=p[len('/api/thread/'):];thread=c.execute('SELECT threads.*,users.name FROM threads JOIN users ON users.id=threads.user WHERE threads.id=?',(tid,)).fetchone()
     if not thread:return self.reply(404,{'error':'Thread not found.'})
     if not self.readable(c,u,thread['scope']):return self.reply(403,{'error':'Join or unlock this chat to open its threads.'})
     return self.reply(200,{'thread':dict(thread),'replies':rows(c,'SELECT thread_replies.*,users.name FROM thread_replies JOIN users ON users.id=thread_replies.user WHERE thread=? ORDER BY created,id',(tid,))})
    if p=='/api/people':
     if not u:return self.reply(401,{'error':'Sign in to find friends.'})
     people=rows(c,'SELECT id,name FROM users WHERE id!=? ORDER BY name COLLATE NOCASE',(u['id'],))
     relations=rows(c,'SELECT * FROM friendships WHERE low=? OR high=?',(u['id'],u['id']))
     for person in people:
      rel=next((r for r in relations if person['id'] in (r['low'],r['high'])),None)
      person['relationship']='friend' if rel and rel['status']=='accepted' else ('sent' if rel['sender']==u['id'] else 'received') if rel else 'none'
     return self.reply(200,people)
    if p=='/api/communities':
     return self.reply(200,rows(c,"SELECT communities.*, (SELECT COUNT(*) FROM community_members WHERE community=communities.id) AS members,EXISTS(SELECT 1 FROM community_members WHERE community=communities.id AND user=?) AS joined FROM communities ORDER BY starter DESC,name COLLATE NOCASE",(u['id'] if u else '',)))
    if p.startswith('/api/community/'):
     cid=p[len('/api/community/'):];community=c.execute('SELECT * FROM communities WHERE id=?',(cid,)).fetchone()
     if not community:return self.reply(404,{'error':'Community not found.'})
     joined=bool(u and c.execute('SELECT 1 FROM community_members WHERE community=? AND user=?',(cid,u['id'])).fetchone())
     messages=rows(c,'SELECT community_messages.*,users.name FROM community_messages JOIN users ON users.id=community_messages.user WHERE community=? ORDER BY created DESC,id DESC LIMIT 300',(cid,))
     return self.reply(200,{'community':dict(community),'joined':joined,'members':c.execute('SELECT COUNT(*) FROM community_members WHERE community=?',(cid,)).fetchone()[0],'messages':list(reversed(messages))})
    if p.startswith('/api/photo-post/'):
     pid=p[len('/api/photo-post/'):]
     visible=feed_records(c,'WHERE feed_posts.id=?',(pid,),viewer=u['id'] if u else '')
     return self.reply(200,visible[0]) if visible else self.reply(404,{'error':'This post is unavailable or belongs to a private profile.'})
    if p.startswith('/api/studio/photo-candidates/'):
     if hosted():return self.reply(403,{'error':'The photo picker only runs locally.'})
     slug=unquote(p[len('/api/studio/photo-candidates/'):])
     artist=next((a for a in artist_records(c) if a['artist_slug']==slug),None)
     if not artist:return self.reply(404,{'error':'Artist not found.'})
     try:return self.reply(200,{'candidates':photo_candidates(artist['artist'],artist_profile(c,slug,artist['artist']))})
     except Exception as error:return self.reply(502,{'error':'Could not reach the photo sources. Try again.'})
    if p=='/api/artist-search':
     query=(parse_qs(urlparse(self.path).query).get('q') or [''])[0]
     try:return self.reply(200,{'results':search_artists(query)})
     except Exception:return self.reply(502,{'error':'Artist search is unavailable right now. Try again in a moment.'})
    if p.startswith('/api/mb-artist/'):
     mbid=p[len('/api/mb-artist/'):]
     if not MBID_RE.match(mbid):return self.reply(404,{'error':'Artist not found.'})
     profile=artist_profile(c,'mb:'+mbid,'',mbid)
     if profile.get('unavailable'):return self.reply(502,{'error':'We couldn’t load this artist right now. Try again in a moment.'})
     if not profile.get('found'):return self.reply(404,{'error':'Artist not found.'})
     local=next((a['artist_slug'] for a in artist_records(c) if artist_identity(a['artist'])==artist_identity(profile['name'])),None)
     return self.reply(200,{**profile,'slug':local,'shows':fan_logged_shows(c,profile['name'])})
    if p.startswith('/api/artist-profile/'):
     slug=unquote(p[len('/api/artist-profile/'):])
     artist=next((a for a in artist_records(c) if a['artist_slug']==slug),None)
     if not artist:return self.reply(404,{'error':'Artist not found.'})
     return self.reply(200,artist_profile(c,slug,artist['artist']))
    if p=='/api/featured-photos':
     posts=feed_records(c,"WHERE feed_posts.featured=1 AND users.visibility='public'",(),viewer='')[:12]
     return self.reply(200,[{'id':x['id'],'photo':x['photo'],'name':x['name'],'artist':x.get('artist'),'venue':x.get('venue'),'city':x.get('city')} for x in posts])
    if p=='/api/feed':return self.reply(200,feed_records(c,viewer=u['id'] if u else ''))
    if p.startswith('/api/feed/'):
     uid=p[len('/api/feed/'):]
     return self.reply(200,feed_records(c,'WHERE feed_posts.user=?',(uid,),viewer=u['id'] if u else ''))
    if p.startswith('/api/profile/'):
     uid=p[len('/api/profile/'):];person=c.execute('SELECT id,name,visibility FROM users WHERE id=?',(uid,)).fetchone()
     if not person:return self.reply(404,{'error':'Profile not found.'})
     result=dict(person);result['can_view']=can_view_profile(c,uid,u['id'] if u else '')
     rel=c.execute('SELECT sender,status FROM friendships WHERE (low=? AND high=?) OR (low=? AND high=?)',(uid,u['id'],u['id'],uid)).fetchone() if u else None
     result['relationship']='self' if u and u['id']==uid else 'friend' if rel and rel['status']=='accepted' else ('sent' if rel['sender']==u['id'] else 'received') if rel else 'none'
     return self.reply(200,result)
    if p.startswith('/api/event-feed/'):
     eid=p[len('/api/event-feed/'):]
     return self.reply(200,feed_records(c,'WHERE feed_posts.event_id=?',(eid,),viewer=u['id'] if u else ''))
    if p.startswith('/api/posts/'):
     scope=unquote(p[len('/api/posts/'):])
     if not self.allowed(c,u,scope):return self.reply(403,{'error':'Check into this event to open its attendee chat.'})
     posts=rows(c,'''SELECT posts.*,users.name,EXISTS(SELECT 1 FROM attendance WHERE attendance.user=posts.user AND attendance.event=?) AS attended FROM posts JOIN users ON users.id=posts.user WHERE scope=? ORDER BY created''',(scope.split(':')[-1] if ':' in scope else '',scope))
     for post in posts:
      post['tags']=json.loads(post['tags'])
      if hosted() and post['photo']:post['photo']='/api/media/post/'+post['id']
     return self.reply(200,posts)
   return self.reply(404,{'error':'Not found'})
  if p in ('/souvenue-logo.svg','/souvenue-wordmark-art.svg','/souvenue-logo-header.png'):
   b=(ROOT/'public'/Path(p).name).read_bytes();self.send_response(200);self.send_header('Content-Type',{'.png':'image/png','.webp':'image/webp'}.get(Path(p).suffix,'image/svg+xml'));self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b);return
  if p.startswith('/marks/'):
   file=ROOT/'public'/'marks'/Path(p).name
   if not file.is_file() or file.suffix!='.svg':return self.reply(404,{'error':'Mark not found.'})
   b=file.read_bytes();self.send_response(200);self.send_header('Content-Type','image/svg+xml');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b);return
  if p.startswith('/artists/'):
   file=ROOT/'public'/'artists'/Path(p).name
   if not file.is_file() or file.suffix!='.jpg':return self.reply(404,{'error':'Photo not found.'})
   b=file.read_bytes();self.send_response(200);self.send_header('Content-Type','image/jpeg');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b);return
  # Vercel serves public/ from its CDN and omits it from the Python bundle.
  # Page navigation must read a template that ships with the server instead.
  file=ROOT/'public'/p.lstrip('/') if p in ('/app.js','/style.css','/flex-carousel.js','/tear-ticket.js','/confetti-floor.js','/stage-lights.js') else ROOT/'templates'/'index.html'
  b=file.read_bytes();self.send_response(200);self.send_header('Content-Type','text/javascript' if file.suffix=='.js' else 'text/css' if file.suffix=='.css' else 'text/html');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
 def readable(self,c,u,scope):
  if scope.startswith('community:'):return bool(c.execute('SELECT 1 FROM communities WHERE id=?',(scope[10:],)).fetchone())
  return self.allowed(c,u,scope)
 def allowed(self,c,u,scope):
  if scope.startswith('community:'):return bool(u and c.execute('SELECT 1 FROM community_members WHERE community=? AND user=?',(scope[10:],u['id'])).fetchone())
  if scope.startswith('venue:'):return scope[6:] in {event['venue_key'] for event in event_records(c)}
  if scope.startswith('city:'):return scope[5:] in [r[0] for r in c.execute('SELECT DISTINCT city FROM events')]
  if ':' not in scope:return False
  kind,event=scope.split(':',1)
  if not c.execute('SELECT 1 FROM events WHERE id=?',(event,)).fetchone():return False
  return kind=='show' or (kind=='chat' and u and c.execute('SELECT 1 FROM attendance WHERE user=? AND event=?',(u['id'],event)).fetchone() is not None)
 def do_POST(self):
  try:
   origin=self.headers.get('Origin')
   allowed={('https://' if hosted() else 'http://')+self.headers.get('Host','')}
   allowed.update(x.strip().rstrip('/') for x in os.environ.get('ALLOWED_ORIGINS','').split(',') if x.strip())
   if origin and origin not in allowed:return self.reply(403,{'error':'Request origin is not allowed.'})
   request_limit=MAX_FEED_REQUEST_BYTES if urlparse(self.path).path=='/api/feed-post' else MAX_REQUEST_BYTES
   if int(self.headers.get('Content-Length',0))>request_limit:return self.reply(413,{'error':'Use smaller photos within the upload limits shown in the app.'})
   data=json.loads(self.rfile.read(int(self.headers.get('Content-Length',0))) or '{}');p=urlparse(self.path).path
   with db() as c:
    u=self.user(c)
    if p in ['/api/register','/api/login']:
     name=str(data.get('name','')).strip();pw=str(data.get('password',''))
     if not 2<=len(name)<=40 or len(pw)<8:return self.reply(400,{'error':'Use a name of 2–40 characters and a password of at least 8 characters.'})
     # Names are case-insensitive: "Gob" and "gob" are the same name. An exact match wins
     # where older accounts already differ only by case.
     r=c.execute('SELECT * FROM users WHERE lower(name)=lower(?) ORDER BY CASE WHEN name=? THEN 0 ELSE 1 END LIMIT 1',(name,name)).fetchone()
     if p=='/api/register':
      if r:return self.reply(409,{'error':'Name already in use. Sign in or choose another name.'})
      salt=secrets.token_hex(16);uid=secrets.token_hex(16);digest=password_digest(pw,salt);c.execute('INSERT INTO users(id,name,password,salt) VALUES(?,?,?,?)',(uid,name,digest,salt))
     else:
      if not r or not password_matches(pw,r['password'],r['salt']):return self.reply(401,{'error':'Name or password is incorrect.'})
      uid=r['id']
     token=secrets.token_urlsafe(32);c.execute('INSERT INTO sessions VALUES(?,?,?)',(token,uid,time.time()+86400*7));c.commit();self.send_response(200);self.send_header('Set-Cookie',f'session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=604800'+('; Secure' if hosted() else ''));self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(b'{}');return
    if p=='/api/logout':
     token=next((v.strip()[8:] for v in self.headers.get('Cookie','').split(';') if v.strip().startswith('session=')), '');c.execute('DELETE FROM sessions WHERE token=?',(token,));return self.reply(200,{})
    if p in ('/api/studio/photo-choice','/api/studio/photo-clear'):
     if hosted():return self.reply(403,{'error':'The photo picker only runs locally.'})
     slug=str(data.get('slug',''))
     if not any(a['artist_slug']==slug for a in artist_records(c)):return self.reply(404,{'error':'Artist not found.'})
     if p=='/api/studio/photo-clear':
      choices=photo_choices();choices.pop(slug,None);PHOTO_CHOICES.write_text(json.dumps(choices,indent=1,ensure_ascii=False)+'\n',encoding='utf-8');return self.reply(200,{'ok':True})
     try:return self.reply(200,save_photo_choice(slug,data.get('choice') or {}))
     except Exception as error:return self.reply(400,{'error':str(error) if isinstance(error,ValueError) else 'Could not save that photo. Try another.'})
    if not u:return self.reply(401,{'error':'Sign in to continue.'})
    if p=='/api/concert-log':
     event_id=data.get('event_id','');event=None
     if event_id:
      event=next((e for e in event_records(c) if e['id']==event_id),None)
      if not event:event=next((e for a in historical_catalog()['artists'].values() for e in a['events'] if e['id']==event_id),None)
      if not event:return self.reply(404,{'error':'Show not found.'})
     artist=str(event['artist'] if event else data.get('artist','')).strip();venue=str(event['venue'] if event else data.get('venue','')).strip();city=str(event['city'] if event else data.get('city','')).strip();day=str((event.get('start_date') or '') if event else data.get('date',''))
     if not all(1<=len(x)<=160 for x in (artist,venue,city)):return self.reply(400,{'error':'Enter an artist, venue, and city (up to 160 characters each).'})
     try:parsed=datetime.strptime(day,'%Y-%m-%d').date()
     except ValueError:return self.reply(400,{'error':'Choose a valid concert date.'})
     if parsed>datetime.now(ZoneInfo('America/New_York')).date():return self.reply(400,{'error':'Only shows on or before today can be logged.'})
     identity=concert_identity(artist,venue,city,day)
     artists_seen=data.get('artists_seen')
     if artists_seen is not None and (not isinstance(artists_seen,list) or len(artists_seen)>30):return self.reply(400,{'error':'Choose up to 30 performers for this show.'})
     normalized=[];seen_keys=set()
     for person in (artists_seen if artists_seen is not None else [{'artist':artist,'artist_slug':event.get('artist_slug','') if event else ''}]):
      if isinstance(person,str):person={'artist':person,'artist_slug':''}
      if not isinstance(person,dict):continue
      name=str(person.get('artist','')).strip()[:160];slug=str(person.get('artist_slug','')).strip()[:160]
      key=slug or artist_identity(name)
      if not name or not key or key in seen_keys:continue
      seen_keys.add(key);normalized.append({'artist':name,'artist_slug':slug})
     # Optional star rating: 0.5-5 in half-star steps; null/0 clears it; omitted keeps the saved one.
     has_rating='rating' in data;rating=data.get('rating')
     if rating in (None,0):rating=None
     elif isinstance(rating,bool) or not isinstance(rating,(int,float)) or not 0.5<=rating<=5 or rating*2!=int(rating*2):return self.reply(400,{'error':'Rate the show from half a star to 5 stars.'})
     else:rating=float(rating)
     log=c.execute('SELECT id,rating FROM concert_logs WHERE user=? AND identity=?',(u['id'],identity)).fetchone()
     log_id=log['id'] if log else secrets.token_hex(16)
     if not has_rating:rating=log['rating'] if log else None
     if not log:c.execute('INSERT INTO concert_logs(id,user,identity,event_id,artist,venue,city,date,created,artists_seen,rating) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(log_id,u['id'],identity,event_id,artist,venue,city,day,time.time(),json.dumps(normalized),rating))
     else:c.execute('UPDATE concert_logs SET artists_seen=?,rating=? WHERE id=? AND user=?',(json.dumps(normalized),rating,log_id,u['id']))
     return self.reply(200,{'ok':True,'artists_seen':normalized,'rating':rating})
    if p=='/api/concert-log-delete':
     c.execute('DELETE FROM concert_logs WHERE id=? AND user=?',(str(data.get('id','')),u['id']))
     return self.reply(200,{'ok':True})
    if p in ('/api/checkin','/api/checkin-gps'):
     event_id=data.get('event')
     if not isinstance(event_id,str):return self.reply(400,{'error':'Choose a show.'})
     event=next((e for e in event_records(c) if e['id']==event_id),None)
     if not event:return self.reply(404,{'error':'Unknown event.'})
     method='gps' if p=='/api/checkin-gps' else 'demo'
     if method=='demo' and not demo_checkins_enabled():return self.reply(403,{'error':'Simulated check-ins are disabled. Use location check-in at the venue.'})
     if method=='gps':
      error=validate_gps(event,data)
      if error:return self.reply(403,{'error':error})
     result=c.execute('INSERT OR IGNORE INTO attendance(user,event,created,method) VALUES(?,?,?,?)',(u['id'],event_id,time.time(),method))
     return self.reply(200,{'ok':True,'method':method,'points_awarded':ATTENDANCE_POINTS if result.rowcount else 0,'total_points':c.execute('SELECT COUNT(*) FROM attendance WHERE user=?',(u['id'],)).fetchone()[0]*ATTENDANCE_POINTS})
    if p in ('/api/thread-delete','/api/thread-reply-delete'):
     target=data.get('id')
     if not isinstance(target,str):return self.reply(400,{'error':'Choose an item to delete.'})
     table='threads' if p=='/api/thread-delete' else 'thread_replies'
     record=c.execute('SELECT * FROM '+table+' WHERE id=?',(target,)).fetchone()
     if not record:return self.reply(404,{'error':'This item was already deleted or could not be found.'})
     if record['user']!=u['id']:return self.reply(403,{'error':'You can only delete your own threads and comments.'})
     if table=='threads':c.execute('DELETE FROM thread_replies WHERE thread=?',(target,))
     c.execute('DELETE FROM '+table+' WHERE id=?',(target,));return self.reply(200,{'ok':True})
    if p=='/api/thread-create':
     scope=str(data.get('scope',''));title=str(data.get('title','')).strip();body=str(data.get('body','')).strip()
     if not self.allowed(c,u,scope):return self.reply(403,{'error':'Join or unlock this chat before starting a thread.'})
     if not 3<=len(title)<=120 or not 1<=len(body)<=5000:return self.reply(400,{'error':'Use a title of 3–120 characters and a post of 1–5,000 characters.'})
     tid=secrets.token_hex(16);c.execute('INSERT INTO threads VALUES(?,?,?,?,?,?)',(tid,scope,u['id'],title,body,time.time()));return self.reply(200,{'id':tid})
    if p=='/api/thread-reply':
     tid=data.get('thread');body=str(data.get('body','')).strip()
     if not isinstance(tid,str):return self.reply(400,{'error':'Choose a thread.'})
     thread=c.execute('SELECT scope FROM threads WHERE id=?',(tid,)).fetchone()
     if not thread:return self.reply(404,{'error':'Thread not found.'})
     if not self.allowed(c,u,thread['scope']):return self.reply(403,{'error':'Join or unlock this chat before commenting.'})
     if not 1<=len(body)<=2000:return self.reply(400,{'error':'Write a comment of 1–2,000 characters.'})
     c.execute('INSERT INTO thread_replies VALUES(?,?,?,?,?)',(secrets.token_hex(16),tid,u['id'],body,time.time()));return self.reply(200,{'ok':True})
    if p=='/api/leaderboard-preference':
     enabled=data.get('enabled')
     if not isinstance(enabled,bool):return self.reply(400,{'error':'Choose whether to appear on leaderboards.'})
     c.execute('UPDATE users SET leaderboard_opt_in=? WHERE id=?',(int(enabled),u['id']));return self.reply(200,{'enabled':enabled})
    if p=='/api/privacy':
     visibility=data.get('visibility')
     if visibility not in ('public','private'):return self.reply(400,{'error':'Choose Public or Private.'})
     c.execute('UPDATE users SET visibility=? WHERE id=?',(visibility,u['id']));return self.reply(200,{'visibility':visibility})
    if p=='/api/friend':
     target=data.get('user');action=data.get('action')
     if not isinstance(target,str) or target==u['id'] or not c.execute('SELECT 1 FROM users WHERE id=?',(target,)).fetchone():return self.reply(400,{'error':'Choose another member.'})
     low,high=sorted([u['id'],target]);rel=c.execute('SELECT * FROM friendships WHERE low=? AND high=?',(low,high)).fetchone()
     if action=='request':
      if not rel:c.execute('INSERT INTO friendships VALUES(?,?,?,?,?)',(low,high,u['id'],'pending',time.time()))
     elif action=='accept':
      if not rel or rel['status']!='pending' or rel['sender']==u['id']:return self.reply(403,{'error':'Only the recipient can accept a request.'})
      c.execute("UPDATE friendships SET status='accepted' WHERE low=? AND high=?",(low,high))
     elif action in ('decline','cancel','remove'):
      if not rel:return self.reply(200,{})
      if (action=='decline' and (rel['status']!='pending' or rel['sender']==u['id'])) or (action=='cancel' and (rel['status']!='pending' or rel['sender']!=u['id'])) or (action=='remove' and rel['status']!='accepted'):return self.reply(403,{'error':'This action is not available.'})
      c.execute('DELETE FROM friendships WHERE low=? AND high=?',(low,high))
     else:return self.reply(400,{'error':'Unknown friend action.'})
     return self.reply(200,{'ok':True})
    if p=='/api/community-create':
     name=str(data.get('name','')).strip();description=str(data.get('description','')).strip()
     if not 3<=len(name)<=70 or not 5<=len(description)<=300:return self.reply(400,{'error':'Use a name of 3–70 characters and a description of 5–300 characters.'})
     category=data.get('category','general')
     if category not in ('artists','venues','tours','general'):return self.reply(400,{'error':'Choose Artists, Venues, Tours, or General.'})
     subcategory=data.get('subcategory','lounge') if category=='general' else 'lounge'
     if subcategory not in GENERAL_TOPICS:return self.reply(400,{'error':'Choose a General topic from the list.'})
     cid=secrets.token_hex(16);c.execute('INSERT INTO communities(id,name,description,topic,creator,starter,created,category,subcategory) VALUES(?,?,?,?,?,?,?,?,?)',(cid,name,description,category.title(),u['id'],0,time.time(),category,subcategory));c.execute('INSERT INTO community_members VALUES(?,?,?)',(cid,u['id'],time.time()))
     return self.reply(200,{'id':cid})
    if p in ('/api/community-join','/api/community-leave','/api/community-message'):
     cid=data.get('community')
     if not isinstance(cid,str) or not c.execute('SELECT 1 FROM communities WHERE id=?',(cid,)).fetchone():return self.reply(404,{'error':'Community not found.'})
     if p=='/api/community-join':c.execute('INSERT OR IGNORE INTO community_members VALUES(?,?,?)',(cid,u['id'],time.time()));return self.reply(200,{'ok':True})
     if p=='/api/community-leave':c.execute('DELETE FROM community_members WHERE community=? AND user=?',(cid,u['id']));return self.reply(200,{'ok':True})
     if not c.execute('SELECT 1 FROM community_members WHERE community=? AND user=?',(cid,u['id'])).fetchone():return self.reply(403,{'error':'Join the community before posting.'})
     body=str(data.get('body','')).strip()
     if not 1<=len(body)<=2000:return self.reply(400,{'error':'Write 1–2,000 characters.'})
     c.execute('INSERT INTO community_messages VALUES(?,?,?,?,?)',(secrets.token_hex(16),cid,u['id'],body,time.time()));return self.reply(200,{'ok':True})
    if p=='/api/feed-post':
     body=str(data.get('body','')).strip();photo=str(data.get('photo',''));event=data.get('event_id') or None;category=data.get('category','general')
     photos=data.get('photos',[photo])
     if not isinstance(photos,list) or not 1<=len(photos)<=10 or any(not isinstance(image,str) or not image.startswith(('data:image/jpeg;base64,','data:image/png;base64,','data:image/webp;base64,')) for image in photos):return self.reply(400,{'error':'Choose 1–10 JPEG, PNG, or WebP photos.'})
     if any(photo_too_large(image) for image in photos):return self.reply(413,{'error':'A photo exceeds the deployment upload limit.'})
     if sum(photo_bytes(image) for image in photos)>MAX_POST_PHOTO_BYTES:return self.reply(413,{'error':'The photos exceed the deployment total upload limit.'})
     photos=[strip_photo_metadata(image) for image in photos];photo=photos[0]
     if len(body)>2000:return self.reply(400,{'error':'Keep your caption under 2,000 characters.'})
     if not photo.startswith(('data:image/jpeg;base64,','data:image/png;base64,','data:image/webp;base64,')):return self.reply(400,{'error':'Add a JPEG, PNG, or WebP photo.'})
     if event is not None and not isinstance(event,str):return self.reply(400,{'error':'Choose a valid show.'})
     if event and not c.execute('SELECT 1 FROM events WHERE id=?',(event,)).fetchone():return self.reply(400,{'error':'Choose a show from the event list.'})
     if category not in ('general','merch') or (category=='merch' and not event):return self.reply(400,{'error':'Tag a show for a merch-stand photo.'})
     postid=secrets.token_hex(16);featured=1 if data.get('featured') is True else 0
     c.execute('INSERT INTO feed_posts(id,user,body,photo,event_id,category,created,extra_photos,featured) VALUES(?,?,?,?,?,?,?,?,?)',(postid,u['id'],body,photo,event,category,time.time(),json.dumps(photos[1:]),featured))
     return self.reply(200,{'id':postid})
    if p=='/api/feed-post-feature':
     pid=data.get('id');on=data.get('featured')
     if not isinstance(pid,str) or not isinstance(on,bool):return self.reply(400,{'error':'Choose a photo post.'})
     if not c.execute('SELECT 1 FROM feed_posts WHERE id=? AND user=?',(pid,u['id'])).fetchone():return self.reply(404,{'error':'Only the person who posted this photo can change that.'})
     c.execute('UPDATE feed_posts SET featured=? WHERE id=? AND user=?',(1 if on else 0,pid,u['id']))
     return self.reply(200,{'ok':True,'featured':on})
    if p=='/api/post':
     scope=str(data.get('scope',''));body=str(data.get('body','')).strip();photo=str(data.get('photo',''))
     if photo_too_large(photo):return self.reply(413,{'error':'A photo exceeds the deployment upload limit.'})
     if not self.allowed(c,u,scope):return self.reply(403,{'error':'This discussion is locked.'})
     if not body or len(body)>2000:return self.reply(400,{'error':'Write 1–2,000 characters.'})
     if photo and not photo.startswith(('data:image/jpeg;base64,','data:image/png;base64,','data:image/webp;base64,')):return self.reply(400,{'error':'Use a JPEG, PNG or WebP photo.'})
     category=str(data.get('category','general'))
     if category not in ('general','merch') or (category=='merch' and (not photo or not scope.startswith('show:'))):return self.reply(400,{'error':'Merch stand posts need a photo and a show.'})
     tags=data.get('tags',[])
     if not isinstance(tags,list) or len(tags)>len(POST_TAGS) or any(not isinstance(tag,str) or tag not in POST_TAGS for tag in tags):return self.reply(400,{'error':'Choose tags from the available show topics.'})
     if tags and not scope.startswith(('show:','chat:')):return self.reply(400,{'error':'Tags belong to show-night discussions.'})
     tags=list(dict.fromkeys(tags))
     if category=='merch' and 'Merch' not in tags:tags.append('Merch')
     c.execute('INSERT INTO posts(id,user,scope,body,photo,created,category,tags) VALUES(?,?,?,?,?,?,?,?)',(secrets.token_hex(16),u['id'],scope,body,strip_photo_metadata(photo),time.time(),category,json.dumps(tags)));return self.reply(200,{'ok':True})
    if p=='/api/event':
     if hosted():return self.reply(403,{'error':'The local event editor is disabled on hosted deployments.'})
     # Local founder tool only; production requires a separate administrator role.
     record=c.execute('SELECT metadata FROM events WHERE id=?',(data.get('id'),)).fetchone()
     if record and json.loads(record[0]).get('source')=='Ticketmaster':return self.reply(403,{'error':'Imported events are updated from their source, not the demo editor.'})
     vals=[str(data.get(k,'')).strip() for k in ['artist','venue','city','date','image']]
     if any(not v or len(v)>160 for v in vals[:4]):return self.reply(400,{'error':'Complete every field (maximum 160 characters each).'})
     if photo_too_large(vals[4]):return self.reply(413,{'error':'Choose an image up to 25 MB.'})
     if vals[4] not in ('forest','violet','amber') and not vals[4].startswith(('data:image/jpeg;base64,','data:image/png;base64,','data:image/webp;base64,')):return self.reply(400,{'error':'Choose a poster style.'})
     c.execute('UPDATE events SET artist=?,venue=?,city=?,date=?,image=? WHERE id=?',(*vals,data.get('id')));return self.reply(200,{'ok':True})
    return self.reply(404,{'error':'Not found'})
  except (ValueError,TypeError):return self.reply(400,{'error':'Invalid request.'})
if __name__=='__main__':
 initialize();port=int(os.environ.get('PORT',4173));print(f'Souvenue is ready at http://127.0.0.1:{port}',flush=True);ThreadingHTTPServer(('127.0.0.1',port),Handler).serve_forever()
