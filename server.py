import os,json,sqlite3,secrets,hashlib,hmac,time,re,unicodedata,math,base64
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from urllib.parse import urlparse,unquote,parse_qs
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
def artist_records(c):
 photo_file=ROOT/'artist-photos.json';photos=json.loads(photo_file.read_text(encoding='utf-8')) if photo_file.exists() else {}
 genre_file=ROOT/'artist-genres.json';genres=json.loads(genre_file.read_text(encoding='utf-8')) if genre_file.exists() else {}
 catalog={s['slug']:{'artist_slug':s['slug'],'id':s['slug'],'artist':s['artist'],'source':'Ticketmaster','source_url':s['source_url'],'imported_at':s['imported_at'],'image':s.get('image','violet'),'tour_label':s.get('tour_label','Upcoming shows & appearances')} for s in source_snapshots()}
 for event in event_records(c):
  if event['artist_slug'] not in catalog:catalog[event['artist_slug']]=event
 for slug,artist in catalog.items():
  artist['artist_photo']=photos.get(slug,{}).get('path','')
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
  if p in ('/souvenue-logo.svg','/souvenue-wordmark-art.svg'):
   b=(ROOT/'public'/Path(p).name).read_bytes();self.send_response(200);self.send_header('Content-Type','image/svg+xml');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b);return
  if p.startswith('/artists/'):
   file=ROOT/'public'/'artists'/Path(p).name
   if not file.is_file() or file.suffix!='.jpg':return self.reply(404,{'error':'Photo not found.'})
   b=file.read_bytes();self.send_response(200);self.send_header('Content-Type','image/jpeg');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b);return
  # Vercel serves public/ from its CDN and omits it from the Python bundle.
  # Page navigation must read a template that ships with the server instead.
  file=ROOT/'public'/p.lstrip('/') if p in ('/app.js','/style.css','/flex-carousel.js','/tear-ticket.js') else ROOT/'templates'/'index.html'
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
     r=c.execute('SELECT * FROM users WHERE name=?',(name,)).fetchone()
     if p=='/api/register':
      if r:return self.reply(409,{'error':'Name already in use. Sign in or choose another name.'})
      salt=secrets.token_hex(16);uid=secrets.token_hex(16);digest=password_digest(pw,salt);c.execute('INSERT INTO users(id,name,password,salt) VALUES(?,?,?,?)',(uid,name,digest,salt))
     else:
      if not r or not password_matches(pw,r['password'],r['salt']):return self.reply(401,{'error':'Name or password is incorrect.'})
      uid=r['id']
     token=secrets.token_urlsafe(32);c.execute('INSERT INTO sessions VALUES(?,?,?)',(token,uid,time.time()+86400*7));c.commit();self.send_response(200);self.send_header('Set-Cookie',f'session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=604800'+('; Secure' if hosted() else ''));self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(b'{}');return
    if p=='/api/logout':
     token=next((v.strip()[8:] for v in self.headers.get('Cookie','').split(';') if v.strip().startswith('session=')), '');c.execute('DELETE FROM sessions WHERE token=?',(token,));return self.reply(200,{})
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
     photo=photos[0]
     if len(body)>2000:return self.reply(400,{'error':'Keep your caption under 2,000 characters.'})
     if not photo.startswith(('data:image/jpeg;base64,','data:image/png;base64,','data:image/webp;base64,')):return self.reply(400,{'error':'Add a JPEG, PNG, or WebP photo.'})
     if event is not None and not isinstance(event,str):return self.reply(400,{'error':'Choose a valid show.'})
     if event and not c.execute('SELECT 1 FROM events WHERE id=?',(event,)).fetchone():return self.reply(400,{'error':'Choose a show from the event list.'})
     if category not in ('general','merch') or (category=='merch' and not event):return self.reply(400,{'error':'Tag a show for a merch-stand photo.'})
     postid=secrets.token_hex(16)
     c.execute('INSERT INTO feed_posts(id,user,body,photo,event_id,category,created,extra_photos) VALUES(?,?,?,?,?,?,?,?)',(postid,u['id'],body,photo,event,category,time.time(),json.dumps(photos[1:])))
     return self.reply(200,{'id':postid})
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
     c.execute('INSERT INTO posts(id,user,scope,body,photo,created,category,tags) VALUES(?,?,?,?,?,?,?,?)',(secrets.token_hex(16),u['id'],scope,body,photo,time.time(),category,json.dumps(tags)));return self.reply(200,{'ok':True})
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
