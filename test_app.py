import base64
"""Exercise real request handlers and database without needing a network port."""
import unittest,tempfile,io,json
from pathlib import Path
import server
class Response:
 def __init__(self,method,path,data=None,cookie=''):
  if path=='/api/register' and data and 'username' not in data:  # most tests only care about the display name
   import re;data={**data,'username':(re.sub(r'[^a-z0-9]+','_',str(data.get('name','')).lower()).strip('_')+'_fan')[:20]}
  h=object.__new__(server.Handler);raw=json.dumps(data or {}).encode();h.path=path;h.headers={'Content-Length':str(len(raw)),'Cookie':cookie};h.rfile=io.BytesIO(raw);h.wfile=io.BytesIO();self.status=None;self.headers={}
  h.send_response=lambda status:setattr(self,'status',status)
  h.send_header=lambda k,v:self.headers.update({k:v})
  h.end_headers=lambda:None
  getattr(h,'do_'+method)();self.data=json.loads(h.wfile.getvalue()) if path.startswith('/api/') else h.wfile.getvalue()
class Flow(unittest.TestCase):
 def test_gps_checkin(self):
  from unittest.mock import patch
  from datetime import datetime,timedelta
  from zoneinfo import ZoneInfo
  import time,math
  with tempfile.TemporaryDirectory() as tmp:
   server.DB=Path(tmp)/'test.sqlite3';server.initialize()
   cookie=Response('POST','/api/register',{'name':'Location fan','password':'demo-pass-123'}).headers['Set-Cookie'].split(';')[0]
   now=time.time();start=datetime.fromtimestamp(now,ZoneInfo('UTC'))
   venue={'venue':'GPS Test Arena','city':'Boston','region':'MA','country':'US'}
   key=server.venue_key(venue);locations={key:{'latitude':42.3662,'longitude':-71.0621}}
   meta={'start_date':start.date().isoformat(),'local_time':start.strftime('%H:%M'),'timezone':'UTC','region':'MA','country':'US','status':'Scheduled'}
   with server.db() as c:
    for eid,changes in [('gps-test',{}),('gps-next-night',{'start_date':(start+timedelta(days=1)).date().isoformat()}),('gps-cancelled',{'status':'Cancelled'}),('gps-no-zone',{'timezone':''}),('gps-date-only',{'local_time':''})]:
     c.execute('INSERT INTO events(id,artist,venue,city,date,image,metadata) VALUES(?,?,?,?,?,?,?)',(eid,'GPS Artist',venue['venue'],venue['city'],meta['start_date'],'violet',json.dumps({**meta,**changes})))
   payload={'event':'gps-test','latitude':42.3662,'longitude':-71.0621,'accuracy':12,'timestamp':now*1000}
   with patch.object(server,'venue_locations',return_value=locations),patch.object(server.time,'time',return_value=now):
    self.assertEqual(Response('POST','/api/checkin-gps',payload).status,401)
    for changes in [{'latitude':0},{'accuracy':1000},{'accuracy':0},{'latitude':True},{'longitude':float('nan')},{'latitude':91},{'timestamp':(now-120)*1000},{'timestamp':(now+120)*1000},{'event':'gps-next-night'},{'event':'gps-cancelled'},{'event':'gps-no-zone'}]:
     self.assertEqual(Response('POST','/api/checkin-gps',{**payload,**changes},cookie).status,403)
    self.assertEqual(Response('GET','/api/posts/chat:gps-test',cookie=cookie).status,403)
    r=Response('POST','/api/checkin-gps',payload,cookie);self.assertEqual(r.status,200);self.assertEqual(r.data['points_awarded'],100)
    self.assertEqual(Response('POST','/api/checkin-gps',payload,cookie).data['points_awarded'],0)
    self.assertEqual(Response('GET','/api/posts/chat:gps-test',cookie=cookie).status,200)
    self.assertEqual(Response('GET','/api/posts/chat:gps-next-night',cookie=cookie).status,403)
    state=Response('GET','/api/state',cookie=cookie).data;self.assertEqual(state['attendance'][0]['method'],'gps');self.assertTrue(state['concert_history'][0]['checked_in']);self.assertEqual(state['points'],100)
    with server.db() as c:
     self.assertNotIn('latitude',[r[1] for r in c.execute('PRAGMA table_info(attendance)')])
    event=next(e for e in state['events'] if e['id']=='gps-test')
    opening=datetime.fromisoformat(event['gps_checkin']['opens_at']).timestamp();closing=datetime.fromisoformat(event['gps_checkin']['closes_at']).timestamp()
    self.assertFalse(server.gps_policy(event,opening-1)['available']);self.assertTrue(server.gps_policy(event,opening)['available']);self.assertFalse(server.gps_policy(event,closing+1)['available'])
    self.assertFalse(server.gps_policy({**event,'venue':'Unknown','venue_key':'unknown'},now)['configured'])
    with patch.dict(server.os.environ,{'SOUVENUE_DEMO_CHECKINS':'0'}):
     self.assertEqual(Response('POST','/api/checkin',{'event':'gps-next-night'},cookie).status,403)
     self.assertFalse(Response('GET','/api/state',cookie=cookie).data['demo_checkins_enabled'])
    with server.db() as c:
     old=c.execute('SELECT method FROM attendance WHERE user=?',(state['user']['id'],)).fetchone()[0];self.assertEqual(old,'gps')
 def test_manual_concert_log(self):
  with tempfile.TemporaryDirectory() as tmp:
   server.DB=Path(tmp)/'test.sqlite3';server.initialize()
   a=Response('POST','/api/register',{'name':'Logger','password':'demo-pass-123'});cookie=a.headers['Set-Cookie'].split(';')[0]
   other=Response('POST','/api/register',{'name':'Other logger','password':'demo-pass-123'}).headers['Set-Cookie'].split(';')[0]
   payload={'artist':'Tame Impala','venue':'TD Garden','city':'Boston','date':'2026-07-28','checked_in':True,'points':99999}
   self.assertEqual(Response('POST','/api/concert-log',payload).status,401)
   for _ in range(2):self.assertEqual(Response('POST','/api/concert-log',payload,cookie).status,200)
   state=Response('GET','/api/state',cookie=cookie).data
   self.assertEqual(len(state['concert_history']),1);self.assertFalse(state['concert_history'][0]['checked_in']);self.assertEqual(state['points'],0);self.assertEqual(state['attendance'],[])
   self.assertEqual(Response('GET','/api/posts/chat:noah-kahan',cookie=cookie).status,403)
   self.assertEqual(Response('POST','/api/concert-log',{**payload,'date':'2099-01-01'},cookie).status,400)
   self.assertEqual(Response('POST','/api/concert-log',{**payload,'date':'2026-02-30'},cookie).status,400)
   self.assertEqual(Response('POST','/api/concert-log',{**payload,'artist':''},cookie).status,400)
   lid=state['concert_history'][0]['id'];Response('POST','/api/concert-log-delete',{'id':lid},other)
   self.assertEqual(len(Response('GET','/api/state',cookie=cookie).data['concert_history']),1)
   with server.db() as c:
    c.execute("INSERT INTO events(id,artist,venue,city,date,image,metadata) VALUES(?,?,?,?,?,?,?)",('past-test','Tame Impala','TD Garden','Boston','Jul 28, 2026','violet',json.dumps({'start_date':'2026-07-28'})))
   Response('POST','/api/checkin',{'event':'past-test'},cookie)
   state=Response('GET','/api/state',cookie=cookie).data
   self.assertEqual(len(state['concert_history']),1);self.assertTrue(state['concert_history'][0]['checked_in']);self.assertEqual(state['points'],100)
   self.assertEqual(Response('POST','/api/concert-log',{**payload,'event_id':'past-test'},cookie).status,200)
   archive=Response('GET','/api/past-events').data
   past=next(e for a in archive['artists'].values() for e in a['events'])
   self.assertEqual(Response('POST','/api/concert-log',{'event_id':past['id']},other).status,200)
   self.assertEqual(Response('GET','/api/state',cookie=other).data['points'],0)
   server.initialize();self.assertEqual(len(Response('GET','/api/state',cookie=other).data['concert_history']),1)
   self.assertEqual(Response('GET','/api/state').data['concert_history'],[])
 def test_photo_metadata_is_stripped(self):
  # A tiny JPEG: SOI, an Exif block holding fake GPS text, APP0, then image data.
  exif=b'Exif\x00\x00GPSLatitude=40.7504'
  app1=b'\xff\xe1'+(len(exif)+2).to_bytes(2,'big')+exif
  app0=b'\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'
  scan=b'\xff\xda\x00\x08\x01\x01\x00\x00?\x00PIXELS\xff\xd9'
  jpeg=b'\xff\xd8'+app1+app0+scan
  url='data:image/jpeg;base64,'+base64.b64encode(jpeg).decode()
  clean=base64.b64decode(server.strip_photo_metadata(url).split(',',1)[1])
  self.assertNotIn(b'GPSLatitude',clean);self.assertIn(b'JFIF',clean);self.assertTrue(clean.endswith(b'PIXELS\xff\xd9'))
  # PNG eXIf chunk and WebP EXIF chunk are removed too.
  chunk=lambda kind,data:len(data).to_bytes(4,'big')+kind+data+b'\0\0\0\0'
  png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',b'x'*13)+chunk(b'eXIf',b'GPS!')+chunk(b'IDAT',b'pix')+chunk(b'IEND',b'')
  self.assertNotIn(b'GPS!',base64.b64decode(server.strip_photo_metadata('data:image/png;base64,'+base64.b64encode(png).decode()).split(',',1)[1]))
  body=b'WEBP'+b'VP8 '+(4).to_bytes(4,'little')+b'pixs'+b'EXIF'+(4).to_bytes(4,'little')+b'GPS!'
  webp=base64.b64decode(server.strip_photo_metadata('data:image/webp;base64,'+base64.b64encode(b'RIFF'+len(body).to_bytes(4,'little')+body).decode()).split(',',1)[1])
  self.assertNotIn(b'GPS!',webp);self.assertEqual(int.from_bytes(webp[4:8],'little'),len(webp)-8)
  with tempfile.TemporaryDirectory() as tmp:
   server.DB=Path(tmp)/'test.sqlite3';server.initialize()
   cookie=Response('POST','/api/register',{'name':'Gps','password':'demo-pass-123'}).headers['Set-Cookie'].split(';')[0]
   pid=Response('POST','/api/feed-post',{'photos':[url,url]},cookie).data['id']
   post=Response('GET','/api/photo-post/'+pid,cookie=cookie).data
   for photo in post['photos']:self.assertNotIn(b'GPSLatitude',base64.b64decode(photo.split(',',1)[1]))
   # Photos stored before stripping existed are cleaned once on startup.
   with server.db() as c:
    c.execute("UPDATE feed_posts SET photo=? WHERE id=?",(url,pid));c.execute("DELETE FROM maintenance")
   server.initialize()
   with server.db() as c:stored=c.execute('SELECT photo FROM feed_posts WHERE id=?',(pid,)).fetchone()[0]
   self.assertNotIn(b'GPSLatitude',base64.b64decode(stored.split(',',1)[1]))
 def test_usernames(self):
  with tempfile.TemporaryDirectory() as tmp:
   server.DB=Path(tmp)/'test.sqlite3';server.initialize()
   reg=lambda name,user,pw='demo-pass-123':Response('POST','/api/register',{'name':name,'username':user,'password':pw})
   self.assertEqual(reg('Gob Bluth','@Gob.Bluth').status,200)  # stored lowercase, @ dropped
   self.assertEqual(reg('Someone','gob.bluth').status,409)
   self.assertEqual(reg('Someone','GOB.BLUTH').status,409)
   for bad in ('ab','has space','way_too_long_for_a_username','émile'):self.assertEqual(reg('Someone',bad).status,400)
   self.assertEqual(reg('Gob Bluth','gob_two').status,200)  # display names can repeat
   for typed in ('gob.bluth','@Gob.Bluth','GOB.BLUTH'):self.assertEqual(Response('POST','/api/login',{'username':typed,'password':'demo-pass-123'}).status,200)
   self.assertEqual(Response('POST','/api/login',{'username':'gob.bluth','password':'wrong-pass-1'}).status,401)
   self.assertEqual(Response('POST','/api/login',{'username':'Gob Bluth','password':'demo-pass-123'}).status,401)  # shared display name is ambiguous
   cookie=Response('POST','/api/login',{'username':'gob_two','password':'demo-pass-123'}).headers['Set-Cookie'].split(';')[0]
   self.assertEqual(Response('GET','/api/state',cookie=cookie).data['user']['username'],'gob_two')
   people=Response('GET','/api/people',cookie=cookie).data
   self.assertEqual([(x['name'],x['username']) for x in people],[('Gob Bluth','gob.bluth')])
 def test_existing_accounts_get_usernames(self):
  import sqlite3
  with tempfile.TemporaryDirectory() as tmp:
   server.DB=Path(tmp)/'test.sqlite3'
   old=sqlite3.connect(server.DB);old.execute('CREATE TABLE users(id TEXT PRIMARY KEY,name TEXT UNIQUE,password TEXT,salt TEXT)')
   salt='abc';digest=server.password_digest('demo-pass-123',salt)
   old.executemany('INSERT INTO users VALUES(?,?,?,?)',[('a','Sofía S',digest,salt),('b','sofia s!',digest,salt),('c','Jo',digest,salt)]);old.commit();old.close()
   server.initialize();server.initialize()  # runs twice safely
   with server.db() as c:handles=dict(c.execute('SELECT id,username FROM users').fetchall())
   self.assertEqual(handles,{'a':'sofia_s','b':'sofia_s2','c':'jo_fan'})
   self.assertEqual(Response('POST','/api/login',{'username':'Jo','password':'demo-pass-123'}).status,200)  # old display-name sign-in still works
   self.assertEqual(Response('POST','/api/register',{'name':'Jo','username':'jo2','password':'demo-pass-123'}).status,200)  # no longer unique
 def test_requested_account_removal(self):
  with tempfile.TemporaryDirectory() as tmp:
   server.DB=Path(tmp)/'test.sqlite3';server.initialize()
   uid,name=server.REMOVED_ACCOUNTS[0]
   with server.db() as c:
    c.execute('DELETE FROM maintenance')
    c.execute("INSERT INTO users(id,name,password,salt) VALUES(?,?,'x','y')",(uid,name))
    c.execute("INSERT INTO users(id,name,password,salt) VALUES('keep','gob','x','y')")
    c.execute("INSERT INTO users(id,name,password,salt) VALUES('same-name-other-id','Gob2','x','y')")
    c.execute("INSERT INTO sessions VALUES('t1',?,9e9)",(uid,))
    c.execute("INSERT INTO friendships VALUES(?,?,?,'accepted',0)",('keep',uid,uid))
   server.initialize()
   with server.db() as c:
    self.assertIsNone(c.execute('SELECT 1 FROM users WHERE id=?',(uid,)).fetchone())
    self.assertIsNotNone(c.execute("SELECT 1 FROM users WHERE id='keep'").fetchone())
    self.assertIsNotNone(c.execute("SELECT 1 FROM users WHERE id='same-name-other-id'").fetchone())
    self.assertIsNone(c.execute('SELECT 1 FROM sessions WHERE user=?',(uid,)).fetchone())
    self.assertIsNone(c.execute('SELECT 1 FROM friendships WHERE low=? OR high=?',(uid,uid)).fetchone())
   # Runs once: a new account reusing the id later is not touched.
   with server.db() as c:c.execute("INSERT INTO users(id,name,password,salt) VALUES(?,?,'x','y')",(uid,name))
   server.initialize()
   with server.db() as c:self.assertIsNotNone(c.execute('SELECT 1 FROM users WHERE id=?',(uid,)).fetchone())
 def test_artist_profile_cache(self):
  with tempfile.TemporaryDirectory() as tmp:
   server.DB=Path(tmp)/'test.sqlite3';server.initialize()
   calls=[];real=server.fetch_artist_profile
   server.fetch_artist_profile=lambda name,*a,**k:(calls.append(name),{'found':True,'name':name,'genres':['pop'],'links':[],'albums':[],'sources':{'musicbrainz':'https://musicbrainz.org/artist/x'}})[1]
   try:
    slug=Response('GET','/api/state').data['artists'][0]['artist_slug']
    first=Response('GET','/api/artist-profile/'+slug).data;second=Response('GET','/api/artist-profile/'+slug).data
    self.assertTrue(first['found']);self.assertEqual(first['genres'],['pop']);self.assertEqual(len(calls),1)  # cached after the first fetch
    self.assertEqual(Response('GET','/api/artist-profile/not-a-real-artist').status,404)
    server.fetch_artist_profile=lambda name,*a,**k:(_ for _ in ()).throw(OSError('offline'))
    with server.db() as c:c.execute('UPDATE artist_profiles SET fetched=0')
    self.assertEqual(Response('GET','/api/artist-profile/'+slug).data['genres'],['pop'])  # stale copy survives an outage
   finally:server.fetch_artist_profile=real
 def test_search_any_artist(self):
  with tempfile.TemporaryDirectory() as tmp:
   server.DB=Path(tmp)/'test.sqlite3';server.initialize();server._artist_search_cache.clear()
   mbid='3ceeddbd-fba5-4bdb-99f7-2d028ed5afda';urls=[];real_get,real_fetch=server.open_get,server.fetch_artist_profile
   tribute='00000000-0000-0000-0000-000000000001';real_post=server.listen_post;server._listens_this_year.clear()
   def fake_get(url,**k):
    if 'listenbrainz' in url:return {'payload':{'total_listen_count':9000 if mbid in url else 5}}
    urls.append(url);return {'artists':[{'id':tribute,'name':'Boygenius tribute','score':100,'tags':[{}]*9},{'id':mbid,'name':'boygenius','score':90,'country':'US'}]}
   server.open_get=fake_get
   server.listen_post=lambda url,payload:[{'artist_mbid':mbid,'total_listen_count':50000},{'artist_mbid':tribute,'total_listen_count':40}]
   server.fetch_artist_profile=lambda name,mbid=None,photo=True:{'found':True,'mbid':mbid,'name':'boygenius','genres':['indie rock'],'links':[],'members':[],'sources':{'musicbrainz':'https://musicbrainz.org/artist/'+mbid}}
   try:
    found=Response('GET','/api/artist-search?q=boyg').data['results']
    self.assertEqual(found[0]['name'],'boygenius')  # the more-listened artist ranks first
    Response('GET','/api/artist-search?q=BOYG');self.assertEqual(len(urls),1)  # cached, case-insensitive
    self.assertEqual(Response('GET','/api/artist-search?q=b').data['results'],[])
    cookie=Response('POST','/api/register',{'name':'Ana','password':'demo-pass-123'}).headers['Set-Cookie'].split(';')[0]
    Response('POST','/api/concert-log',{'artist':'boygenius','venue':'Forest Hills Stadium','city':'Queens','date':'2023-07-01','artists_seen':[{'artist':'boygenius'}]},cookie)
    page=Response('GET','/api/mb-artist/'+mbid).data
    self.assertEqual(page['name'],'boygenius');self.assertIsNone(page['slug'])
    self.assertEqual([(x['venue'],x['fans']) for x in page['shows']],[('Forest Hills Stadium',1)])
    self.assertEqual(Response('GET','/api/mb-artist/not-an-id').status,404)
   finally:server.open_get,server.fetch_artist_profile,server.listen_post=real_get,real_fetch,real_post
 def test_artist_marks_listed(self):
  with tempfile.TemporaryDirectory() as tmp:
   server.DB=Path(tmp)/'test.sqlite3';server.initialize()
   artists=Response('GET','/api/state').data['artists']
   self.assertTrue(artists and all(a['artist_mark']==f"/marks/{a['artist_slug']}.svg" for a in artists))
   for a in artists:self.assertTrue((Path(server.ROOT)/'public'/a['artist_mark'].lstrip('/')).exists())
 def test_profile_with_missing_details(self):
  real=server.open_get
  server.open_get=lambda url,**k:{'id':'f8c0e145-2d97-4c6f-a746-2fe8b33582eb','name':'Mimicking Mars','type':'Group','life-span':{'begin':None},'begin-area':None,'relations':[],'genres':[]}
  try:
   profile=server.fetch_artist_profile('',mbid='f8c0e145-2d97-4c6f-a746-2fe8b33582eb',photo=False)
   self.assertTrue(profile['found']);self.assertIsNone(profile['active_since'])  # small bands often have no start year
  finally:server.open_get=real
 def test_featured_photos(self):
  with tempfile.TemporaryDirectory() as tmp:
   server.DB=Path(tmp)/'test.sqlite3';server.initialize()
   pix='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=='
   def account(name):return Response('POST','/api/register',{'name':name,'password':'demo-pass-123'}).headers['Set-Cookie'].split(';')[0]
   ana,ben=account('Ana'),account('Ben')
   post=lambda cookie,featured:Response('POST','/api/feed-post',{'photos':[pix],'featured':featured},cookie).data['id']
   shown,hidden=post(ana,True),post(ana,False)
   featured=lambda:[x['id'] for x in Response('GET','/api/featured-photos').data]
   self.assertEqual(featured(),[shown])
   self.assertEqual(Response('POST','/api/feed-post-feature',{'id':shown,'featured':False},ben).status,404)
   self.assertEqual(featured(),[shown])
   self.assertEqual(Response('POST','/api/feed-post-feature',{'id':hidden,'featured':True},ana).status,200)
   self.assertEqual(sorted(featured()),sorted([shown,hidden]))
   Response('POST','/api/privacy',{'visibility':'private'},ana)
   self.assertEqual(featured(),[])
   self.assertEqual(Response('POST','/api/feed-post-feature',{'id':shown,'featured':'yes'},ana).status,400)
 def test_concert_rating(self):
  with tempfile.TemporaryDirectory() as tmp:
   server.DB=Path(tmp)/'test.sqlite3';server.initialize()
   cookie=Response('POST','/api/register',{'name':'Rater','password':'demo-pass-123'}).headers['Set-Cookie'].split(';')[0]
   payload={'artist':'Tame Impala','venue':'TD Garden','city':'Boston','date':'2026-07-28'}
   rating=lambda:Response('GET','/api/state',cookie=cookie).data['concert_history'][0].get('rating')
   self.assertEqual(Response('POST','/api/concert-log',{**payload,'rating':3.5},cookie).status,200);self.assertEqual(rating(),3.5)
   for bad in (0.25,5.5,-1,'4',True,[4]):self.assertEqual(Response('POST','/api/concert-log',{**payload,'rating':bad},cookie).status,400)
   self.assertEqual(rating(),3.5)
   Response('POST','/api/concert-log',{**payload,'artists_seen':[{'artist':'Tame Impala'},{'artist':'Opener'}]},cookie);self.assertEqual(rating(),3.5)
   Response('POST','/api/concert-log',{**payload,'rating':5},cookie);self.assertEqual(rating(),5)
   Response('POST','/api/concert-log',{**payload,'rating':None},cookie);self.assertIsNone(rating())
   Response('POST','/api/concert-log',{**payload,'rating':0.5},cookie)
   with server.db() as c:
    c.execute("INSERT INTO events(id,artist,venue,city,date,image,metadata) VALUES(?,?,?,?,?,?,?)",('past-rated','Tame Impala','TD Garden','Boston','Jul 28, 2026','violet',json.dumps({'start_date':'2026-07-28'})))
   Response('POST','/api/checkin',{'event':'past-rated'},cookie);self.assertEqual(rating(),0.5)
 def test_complete_journey(self):
  with tempfile.TemporaryDirectory() as tmp:
   server.DB=Path(tmp)/'test.sqlite3';server.initialize()
   self.assertEqual(Response('GET','/api/posts/show:noah-kahan').status,200)
   self.assertEqual(Response('GET','/api/posts/city:New%20York').status,200)
   self.assertEqual(Response('GET','/api/posts/chat:noah-kahan').status,403)
   self.assertEqual(Response('POST','/api/checkin',{'event':'noah-kahan'}).status,401)
   a=Response('POST','/api/register',{'name':'Founder','password':'demo-pass-123'});self.assertEqual(a.status,200);cookie=a.headers['Set-Cookie'].split(';')[0]
   self.assertIn('HttpOnly',a.headers['Set-Cookie'])
   self.assertEqual(Response('POST','/api/post',{'scope':'show:olivia-rodrigo','body':'Public without attendance'},cookie).status,200)
   self.assertEqual(Response('POST','/api/post',{'scope':'chat:olivia-rodrigo','body':'Denied'},cookie).status,403)
   for _ in range(2):self.assertEqual(Response('POST','/api/checkin',{'event':'noah-kahan'},cookie).status,200)
   state=Response('GET','/api/state',cookie=cookie).data;self.assertEqual(len(state['attendance']),1)
   # A check-in with no manual log still counts its headliner as an artist seen
   self.assertEqual(state['concert_history'][0]['artists_seen'][0]['artist'],'Noah Kahan');self.assertEqual(state['artists_seen_count'],1)
   self.assertEqual(Response('GET','/api/posts/chat:noah-kahan',cookie=cookie).status,200)
   self.assertEqual(Response('GET','/api/posts/chat:olivia-rodrigo',cookie=cookie).status,403)
   self.assertEqual(Response('POST','/api/post',{'scope':'show:noah-kahan','body':'Hello!','photo':'data:image/png;base64,abcd'},cookie).status,200)
   self.assertEqual(Response('GET','/api/posts/show:noah-kahan').data[0]['attended'],1)
   # The Merch stand category is gone: an old client sending it just makes a normal post.
   self.assertEqual(Response('POST','/api/post',{'scope':'show:noah-kahan','body':'Merch stand display','photo':'data:image/png;base64,abcd','category':'merch'},cookie).status,200)
   self.assertEqual(Response('GET','/api/posts/show:noah-kahan').data[-1]['category'],'general')
   self.assertEqual(Response('GET','/api/posts/show:olivia-rodrigo').data[0]['attended'],0)
   self.assertEqual(Response('POST','/api/checkin',{'event':'missing'},cookie).status,404)
   data=dict(next(event for event in state['events'] if event['id']=='noah-kahan'));data['artist']='Editable artist';self.assertEqual(Response('POST','/api/event',data,cookie).status,200)
   updated=next(event for event in Response('GET','/api/state',cookie=cookie).data['events'] if event['id']==data['id'])
   self.assertEqual(updated['artist'],'Editable artist')
   tagged={'scope':'show:noah-kahan','body':'Where is the merch stand?','tags':['Merch','Questions','Merch']}
   self.assertEqual(Response('POST','/api/post',tagged,cookie).status,200)
   saved=Response('GET','/api/posts/show:noah-kahan').data[-1]
   self.assertEqual(saved['tags'],['Merch','Questions'])
   self.assertEqual(Response('POST','/api/post',{**tagged,'tags':['Invalid']},cookie).status,400)
   self.assertEqual(Response('POST','/api/post',{**tagged,'tags':'Merch'},cookie).status,400)
   self.assertEqual(Response('POST','/api/post',{**tagged,'scope':'chat:olivia-rodrigo'},cookie).status,403)
   self.assertFalse(any(p['body']==tagged['body'] for p in Response('GET','/api/posts/show:olivia-rodrigo').data))
   self.assertFalse([p for p in Response('GET','/api/posts/show:noah-kahan').data if p['category']=='merch'])
   self.assertEqual(Response('POST','/api/post',{**tagged,'scope':'chat:noah-kahan','tags':['Stories']},cookie).status,200)
   self.assertEqual(Response('GET','/api/posts/chat:noah-kahan',cookie=cookie).data[-1]['tags'],['Stories'])
   imported=[e for e in state['events'] if e['source']=='Ticketmaster']
   self.assertGreater(len(imported),0)
   first,second=imported[:2]
   self.assertEqual(Response('GET','/api/posts/show:'+first['id']).status,200)
   self.assertEqual(Response('POST','/api/checkin',{'event':first['id']},cookie).status,200)
   self.assertEqual(Response('GET','/api/posts/chat:'+first['id'],cookie=cookie).status,200)
   self.assertEqual(Response('GET','/api/posts/chat:'+second['id'],cookie=cookie).status,403)
   self.assertEqual(Response('POST','/api/event',first,cookie).status,403)
   server.initialize()
   self.assertEqual(len(Response('GET','/api/state').data['events']),len(state['events']))
   self.assertEqual(Response('POST','/api/logout',{},cookie).status,200)
   self.assertIsNone(Response('GET','/api/state',cookie=cookie).data['user'])
   self.assertEqual(Response('POST','/api/login',{'name':'Founder','password':'incorrect'}).status,401)
   self.assertEqual(Response('POST','/api/login',{'name':'Founder','password':'demo-pass-123'}).status,200)
 def test_import_quality(self):
  snapshot=json.loads((Path(__file__).parent/'ticketmaster-events.json').read_text())
  events=snapshot['events'];self.assertEqual(len(events),len(set(e['id'] for e in events)))
  self.assertFalse(any('PREMIUM PACKAGES' in e['title'].upper() or 'PRESTATION' in e['title'].upper() for e in events))
  upcoming=[e for e in events if e['start_date']>='2026-10-30']
  self.assertEqual(len([e for e in upcoming if e['city']=='Amsterdam']),4)
  self.assertEqual(len([e for e in upcoming if e['city']=='Nanterre']),2)
  self.assertEqual(upcoming[0]['start_date'],'2026-10-30')
  self.assertEqual(upcoming[0]['venue'],'Schottenstein Center')
  self.assertEqual(upcoming[-1]['start_date'],'2027-05-10')
  self.assertTrue(all(e['source_url'].startswith('https://') for e in events))
 def test_multiartist_catalog(self):
  snapshots=server.source_snapshots()
  self.assertTrue({'olivia-rodrigo','noah-kahan','sombr','phoebe-bridgers','gracie-abrams','charli-xcx','tame-impala'}.issubset({s['slug'] for s in snapshots}))
  self.assertEqual(len(snapshots),50)
  events=[e for snapshot in snapshots for e in snapshot['events']]
  self.assertEqual(len(events),len({e['id'] for e in events}))
  for snapshot in snapshots:
   self.assertGreaterEqual(snapshot['source_count'],len(snapshot['events']))
   self.assertTrue(snapshot['source_url'].startswith('https://www.ticketmaster.com/'+snapshot['slug']))
   self.assertTrue(all(e['artist_slug']==snapshot['slug'] for e in snapshot['events']))
   self.assertFalse(any(any(word in e['title'].upper() for word in ['VINYL ROOM','SHUTTLE','FAST TRACK','BISTRONOMY']) for e in snapshot['events']))
  with tempfile.TemporaryDirectory() as tmp:
   server.DB=Path(tmp)/'catalog.sqlite3';server.initialize()
   state=Response('GET','/api/state').data
   self.assertEqual(len(state['artists']),50)
   self.assertTrue(all(isinstance(a['genres'],list) for a in state['artists']))
   self.assertIn('Pop',next(a for a in state['artists'] if a['artist_slug']=='olivia-rodrigo')['genres'])
   self.assertEqual(len([e for e in state['events'] if e['source']=='Demo']),2)
   self.assertTrue(any(e['artist_slug']=='noah-kahan' and e['source']=='Ticketmaster' for e in state['events']))
   before={e['id'] for e in state['events']};server.initialize()
   self.assertEqual(before,{e['id'] for e in Response('GET','/api/state').data['events']})
 def test_personal_photo_feeds(self):
  with tempfile.TemporaryDirectory() as tmp:
   server.DB=Path(tmp)/'feeds.sqlite3';server.initialize()
   def account(name):
    r=Response('POST','/api/register',{'name':name,'password':'test-password-123'})
    cookie=r.headers['Set-Cookie'].split(';')[0]
    return cookie,Response('GET','/api/state',cookie=cookie).data['user']['id']
   alice,alice_id=account('Alice');bob,bob_id=account('Bob')
   image='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6RUAAAAAASUVORK5CYII='
   payload={'body':'My night <3','photo':image,'event_id':'noah-kahan','user':bob_id}
   self.assertEqual(Response('POST','/api/feed-post',payload).status,401)
   self.assertEqual(Response('POST','/api/feed-post',payload,alice).status,200)
   self.assertEqual(Response('POST','/api/feed-post',{'body':'No event needed','photo':image},bob).status,200)
   global_posts=Response('GET','/api/feed').data
   self.assertEqual(len(global_posts),2)
   own=Response('GET','/api/feed/'+alice_id).data
   self.assertEqual(len(own),1);self.assertEqual(own[0]['user'],alice_id)
   self.assertEqual(own[0]['artist'],'Noah Kahan');self.assertEqual(own[0]['attended'],0)
   self.assertEqual(len(Response('GET','/api/event-feed/noah-kahan').data),1)
   self.assertEqual(Response('GET','/api/event-feed/olivia-rodrigo').data,[])
   self.assertEqual(Response('GET','/api/posts/show:noah-kahan').data,[])
   self.assertEqual(Response('GET','/api/state',cookie=alice).data['attendance'],[])
   self.assertEqual(Response('GET','/api/posts/chat:noah-kahan',cookie=alice).status,403)
   self.assertEqual(set(Response('GET','/api/profile/'+alice_id).data),{'id','name','username','visibility','can_view','relationship','blocked'})
   self.assertEqual(Response('GET','/api/profile/unknown').status,404)
   self.assertEqual(Response('POST','/api/feed-post',{**payload,'event_id':'unknown'},alice).status,400)
   self.assertEqual(Response('POST','/api/feed-post',{**payload,'photo':''},alice).status,400)
   self.assertEqual(Response('POST','/api/feed-post',{**payload,'category':'merch'},alice).status,200)  # category ignored now
   self.assertEqual(Response('POST','/api/checkin',{'event':'noah-kahan'},alice).status,200)
   self.assertTrue(all(p['attended'] for p in Response('GET','/api/feed/'+alice_id).data))
   self.assertFalse(Response('GET','/api/feed/'+bob_id).data[0]['attended'])
   server.initialize();self.assertEqual(len(Response('GET','/api/feed').data),3)
 def test_friends_and_communities(self):
  with tempfile.TemporaryDirectory() as tmp:
   server.DB=Path(tmp)/'social.sqlite3';server.initialize()
   def account(name):
    response=Response('POST','/api/register',{'name':name,'password':'password-test-123'})
    cookie=response.headers['Set-Cookie'].split(';')[0]
    return cookie,Response('GET','/api/state',cookie=cookie).data['user']['id']
   alice,aid=account('Alice');bob,bid=account('Bob');eve,eid=account('Eve')
   self.assertEqual(Response('GET','/api/people').status,401)
   self.assertEqual(Response('POST','/api/friend',{'user':bid,'action':'request'},alice).status,200)
   self.assertEqual(Response('POST','/api/friend',{'user':bid,'action':'request'},alice).status,200)
   self.assertEqual(next(p for p in Response('GET','/api/people',cookie=bob).data if p['id']==aid)['relationship'],'received')
   self.assertEqual(Response('POST','/api/friend',{'user':bid,'action':'accept'},alice).status,403)
   self.assertEqual(Response('POST','/api/friend',{'user':aid,'action':'accept'},bob).status,200)
   self.assertEqual(next(p for p in Response('GET','/api/people',cookie=alice).data if p['id']==bid)['relationship'],'friend')
   self.assertEqual(next(p for p in Response('GET','/api/people',cookie=eve).data if p['id']==bid)['relationship'],'none')
   self.assertEqual(Response('POST','/api/friend',{'user':aid,'action':'request'},alice).status,400)
   self.assertEqual(Response('POST','/api/friend',{'user':bid,'action':'remove'},alice).status,200)
   self.assertEqual(Response('POST','/api/friend',{'user':bid,'action':'request'},alice).status,200)
   self.assertEqual(Response('POST','/api/friend',{'user':aid,'action':'decline'},bob).status,200)
   rooms=Response('GET','/api/communities').data;baseline_count=len(rooms);self.assertGreaterEqual(baseline_count,100);self.assertTrue(all(r['members']==0 for r in rooms))
   cid=rooms[0]['id']
   self.assertEqual(Response('GET','/api/community/'+cid,cookie=alice).status,200)
   self.assertEqual(Response('POST','/api/community-message',{'community':cid,'body':'No access'},eve).status,403)
   for _ in range(2):self.assertEqual(Response('POST','/api/community-join',{'community':cid},alice).status,200)
   self.assertEqual(Response('GET','/api/community/'+cid,cookie=alice).data['members'],1)
   self.assertEqual(Response('POST','/api/community-message',{'community':cid,'body':'Hello crowd'},alice).status,200)
   self.assertEqual(Response('GET','/api/community/'+cid,cookie=eve).status,200)
   Response('POST','/api/community-join',{'community':cid},bob)
   self.assertEqual(Response('GET','/api/community/'+cid,cookie=bob).data['messages'][0]['body'],'Hello crowd')
   Response('POST','/api/community-leave',{'community':cid},alice)
   self.assertEqual(Response('GET','/api/community/'+cid,cookie=alice).status,200)
   custom=Response('POST','/api/community-create',{'name':'Our concert group','description':'A group for our next night out','category':'venues'},alice)
   self.assertEqual(custom.status,200)
   self.assertEqual(Response('GET','/api/community/'+custom.data['id'],cookie=alice).data['community']['category'],'venues')
   self.assertEqual(Response('POST','/api/community-create',{'name':'Invalid category','description':'Some description here','category':'unknown'},alice).status,400)
   categorized=Response('GET','/api/communities').data
   self.assertEqual(len([r for r in categorized if r['category']=='artists']),50)
   self.assertEqual(len([r for r in categorized if r['category']=='venues']),31)
   self.assertGreater(len([r for r in categorized if r['category']=='tours']),5)
   self.assertTrue(server.GENERAL_TOPICS.issubset({r['subcategory'] for r in categorized if r['category']=='general'}))
   self.assertEqual(Response('GET','/api/community/'+custom.data['id'],cookie=alice).data['members'],1)
   self.assertEqual(Response('GET','/api/community/'+custom.data['id'],cookie=bob).status,200)
   server.initialize();self.assertEqual(len(Response('GET','/api/communities').data),baseline_count+1)
   general=Response('POST','/api/community-create',{'name':'Outfit ideas','description':'Planning what to wear','category':'general','subcategory':'outfits'},alice)
   self.assertEqual(general.status,200)
   self.assertEqual(Response('GET','/api/community/'+general.data['id'],cookie=alice).data['community']['subcategory'],'outfits')
   self.assertEqual(Response('POST','/api/community-create',{'name':'Invalid topic','description':'A description','category':'general','subcategory':'invalid'},alice).status,400)
 def test_profile_privacy(self):
  with tempfile.TemporaryDirectory() as tmp:
   server.DB=Path(tmp)/'privacy.sqlite3';server.initialize()
   def account(name):
    r=Response('POST','/api/register',{'name':name,'password':'test-password-123'})
    cookie=r.headers['Set-Cookie'].split(';')[0]
    return cookie,Response('GET','/api/state',cookie=cookie).data['user']['id']
   owner,uid=account('Owner');friend,fid=account('Friend');stranger,sid=account('Stranger')
   Response('POST','/api/feed-post',{'body':'Private memory','photo':'data:image/png;base64,test','event_id':'noah-kahan'},owner)
   self.assertEqual(len(Response('GET','/api/feed').data),1)
   self.assertEqual(Response('POST','/api/privacy',{'visibility':'private'}).status,401)
   self.assertEqual(Response('POST','/api/privacy',{'visibility':'invalid'},owner).status,400)
   self.assertEqual(Response('POST','/api/privacy',{'visibility':'private','user':sid},owner).status,200)
   self.assertEqual(Response('GET','/api/state',cookie=owner).data['user']['visibility'],'private')
   self.assertEqual(Response('GET','/api/state',cookie=stranger).data['user']['visibility'],'public')
   for cookie in ('',friend,stranger):
    self.assertFalse(Response('GET','/api/profile/'+uid,cookie=cookie).data['can_view'])
    for route in ('/api/feed','/api/feed/'+uid,'/api/event-feed/noah-kahan'):
     self.assertEqual(Response('GET',route,cookie=cookie).data,[])
   self.assertEqual(len(Response('GET','/api/feed/'+uid,cookie=owner).data),1)
   Response('POST','/api/friend',{'user':uid,'action':'request'},friend)
   self.assertEqual(Response('GET','/api/feed/'+uid,cookie=friend).data,[])
   Response('POST','/api/friend',{'user':fid,'action':'accept'},owner)
   self.assertTrue(Response('GET','/api/profile/'+uid,cookie=friend).data['can_view'])
   for route in ('/api/feed','/api/feed/'+uid,'/api/event-feed/noah-kahan'):
    self.assertEqual(len(Response('GET',route,cookie=friend).data),1)
   self.assertEqual(Response('GET','/api/feed',cookie=stranger).data,[])
   Response('POST','/api/friend',{'user':fid,'action':'remove'},owner)
   self.assertEqual(Response('GET','/api/feed/'+uid,cookie=friend).data,[])
   Response('POST','/api/post',{'scope':'show:noah-kahan','body':'Public discussion'},owner)
   self.assertEqual(len(Response('GET','/api/posts/show:noah-kahan').data),1)
   server.initialize();self.assertEqual(Response('GET','/api/state',cookie=owner).data['user']['visibility'],'private')
   Response('POST','/api/privacy',{'visibility':'public'},owner)
   self.assertEqual(len(Response('GET','/api/feed').data),1)
 def test_shared_venue_chat(self):
  with tempfile.TemporaryDirectory() as tmp:
   server.DB=Path(tmp)/'venues.sqlite3';server.initialize()
   with server.db() as c:
    for eid,artist,venue,city in [('night-1','Olivia Rodrigo','TD Garden','Boston'),('night-2','Olivia Rodrigo','TD Garden','Boston'),('night-3','Olivia Rodrigo','TD Garden','Boston'),('other-artist','Another artist','TD Garden','Boston'),('other-venue','Olivia Rodrigo','Another venue','Boston'),('other-city','Olivia Rodrigo','TD Garden','Another city')]:
     c.execute('INSERT INTO events(id,artist,venue,city,date,image) VALUES(?,?,?,?,?,?)',(eid,artist,venue,city,'Test date','violet'))
   events={e['id']:e for e in Response('GET','/api/state').data['events']}
   key=events['night-1']['venue_key']
   self.assertTrue(all(events[eid]['venue_key']==key for eid in ['night-2','night-3','other-artist']))
   self.assertNotEqual(events['other-venue']['venue_key'],key)
   self.assertNotEqual(events['other-city']['venue_key'],key)
   scope='venue:'+key
   self.assertEqual(Response('GET','/api/posts/'+scope).status,200)
   reg=Response('POST','/api/register',{'name':'Venue fan','password':'test-password-123'});cookie=reg.headers['Set-Cookie'].split(';')[0]
   self.assertEqual(Response('POST','/api/post',{'scope':scope,'body':'Which entrance is best?'},cookie).status,200)
   for eid in ['night-1','night-2','night-3','other-artist']:
    posts=Response('GET','/api/posts/venue:'+events[eid]['venue_key']).data
    self.assertEqual(posts[0]['body'],'Which entrance is best?')
   self.assertEqual(Response('GET','/api/posts/venue:'+events['other-venue']['venue_key']).data,[])
   self.assertEqual(Response('GET','/api/posts/venue:unknown').status,403)
   self.assertEqual(Response('GET','/api/state',cookie=cookie).data['attendance'],[])
   Response('POST','/api/checkin',{'event':'night-1'},cookie)
   self.assertEqual(Response('GET','/api/posts/chat:night-2',cookie=cookie).status,403)
 def test_chat_threads(self):
  with tempfile.TemporaryDirectory() as tmp:
   server.DB=Path(tmp)/'threads.sqlite3';server.initialize()
   def account(name):
    r=Response('POST','/api/register',{'name':name,'password':'test-password-123'})
    return r.headers['Set-Cookie'].split(';')[0]
   owner=account('Thread starter');reader=account('Reader')
   payload={'scope':'show:noah-kahan','title':'Meetup before the show','body':'Where should we meet?'}
   self.assertEqual(Response('POST','/api/thread-create',payload).status,401)
   public=Response('POST','/api/thread-create',payload,owner);self.assertEqual(public.status,200);tid=public.data['id']
   self.assertEqual(Response('GET','/api/thread/'+tid).status,200)
   self.assertEqual(len(Response('GET','/api/threads/show%3Anoah-kahan').data),1)
   self.assertEqual(Response('GET','/api/threads/show%3Aolivia-rodrigo').data,[])
   self.assertEqual(Response('POST','/api/thread-reply',{'thread':tid,'body':'I am in!'},reader).status,200)
   self.assertEqual(Response('GET','/api/thread/'+tid).data['replies'][0]['body'],'I am in!')
   self.assertEqual(Response('GET','/api/threads/show:noah-kahan').data[0]['replies'],1)
   self.assertEqual(Response('POST','/api/thread-create',{**payload,'scope':'chat:noah-kahan'},owner).status,403)
   Response('POST','/api/checkin',{'event':'noah-kahan'},owner)
   private=Response('POST','/api/thread-create',{**payload,'scope':'chat:noah-kahan'},owner).data['id']
   self.assertEqual(Response('GET','/api/thread/'+private,cookie=reader).status,403)
   self.assertEqual(Response('POST','/api/thread-reply',{'thread':private,'body':'No access'},reader).status,403)
   cid='charli-xcx-fans';Response('POST','/api/community-join',{'community':cid},owner)
   group=Response('POST','/api/thread-create',{**payload,'scope':'community:'+cid},owner).data['id']
   self.assertEqual(Response('GET','/api/threads/community:'+cid,cookie=reader).status,200)
   self.assertEqual(Response('GET','/api/thread/'+group,cookie=reader).status,200)
   self.assertEqual(Response('POST','/api/thread-reply',{'thread':group,'body':'Must join first'},reader).status,403)
   Response('POST','/api/community-join',{'community':cid},reader)
   self.assertEqual(Response('GET','/api/thread/'+group,cookie=reader).status,200)
   Response('POST','/api/community-leave',{'community':cid},reader)
   self.assertEqual(Response('GET','/api/thread/'+group,cookie=reader).status,200)
   self.assertEqual(Response('POST','/api/thread-reply',{'thread':tid,'body':''},reader).status,400)
   self.assertEqual(Response('GET','/api/thread/unknown').status,404)
   self.assertEqual(Response('GET','/api/posts/show:noah-kahan').data,[])
   server.initialize();self.assertEqual(Response('GET','/api/thread/'+tid).data['thread']['title'],payload['title'])
   replyid=Response('GET','/api/thread/'+tid).data['replies'][0]['id']
   self.assertEqual(Response('POST','/api/thread-reply-delete',{'id':replyid},owner).status,403)
   self.assertEqual(Response('POST','/api/thread-delete',{'id':tid},reader).status,403)
   self.assertEqual(Response('POST','/api/thread-reply-delete',{'id':replyid}).status,401)
   self.assertEqual(Response('POST','/api/thread-reply-delete',{'id':replyid},reader).status,200)
   self.assertEqual(Response('GET','/api/thread/'+tid).data['replies'],[])
   self.assertEqual(Response('GET','/api/threads/show:noah-kahan').data[0]['replies'],0)
   Response('POST','/api/thread-reply',{'thread':tid,'body':'Another comment'},reader)
   self.assertEqual(Response('POST','/api/thread-delete',{'id':tid},owner).status,200)
   self.assertEqual(Response('GET','/api/thread/'+tid).status,404)
   self.assertEqual(Response('GET','/api/threads/show:noah-kahan').data,[])
   self.assertEqual(Response('POST','/api/thread-reply',{'thread':tid,'body':'Too late'},reader).status,404)
   with server.db() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM thread_replies WHERE thread=?',(tid,)).fetchone()[0],0)

 def test_carousel_posts(self):
  with tempfile.TemporaryDirectory() as tmp:
   server.DB=Path(tmp)/'carousels.sqlite3';server.initialize()
   r=Response('POST','/api/register',{'name':'Photo fan','password':'test-password-123'});cookie=r.headers['Set-Cookie'].split(';')[0]
   uid=Response('GET','/api/state',cookie=cookie).data['user']['id']
   photos=['data:image/png;base64,AAAA','data:image/jpeg;base64,BBBB','data:image/webp;base64,CCCC']
   payload={'photos':photos,'body':'Our night in three photos','event_id':'noah-kahan'}
   created=Response('POST','/api/feed-post',payload,cookie);self.assertEqual(created.status,200);pid=created.data['id']
   self.assertEqual(Response('GET','/api/photo-post/'+pid).data['photos'],photos)
   self.assertEqual(Response('GET','/api/photo-post/unknown').status,404)
   for route in ['/api/feed','/api/feed/'+uid,'/api/event-feed/noah-kahan']:
    post=Response('GET',route).data[0];self.assertEqual(post['photos'],photos);self.assertEqual(post['photo'],photos[0])
   for invalid in [[],photos*4,'not a list',['data:text/html;base64,AAAA']]:
    self.assertEqual(Response('POST','/api/feed-post',{**payload,'photos':invalid},cookie).status,400)
   Response('POST','/api/privacy',{'visibility':'private'},cookie)
   self.assertEqual(Response('GET','/api/event-feed/noah-kahan').data,[])
   self.assertEqual(Response('GET','/api/photo-post/'+pid).status,404)
   self.assertEqual(Response('GET','/api/photo-post/'+pid,cookie=cookie).data['photos'],photos)
   self.assertEqual(Response('GET','/api/feed/'+uid,cookie=cookie).data[0]['photos'],photos)
   server.initialize();self.assertEqual(Response('GET','/api/feed/'+uid,cookie=cookie).data[0]['photos'],photos)
 def test_points_and_leaderboards(self):
  with tempfile.TemporaryDirectory() as tmp:
   server.DB=Path(tmp)/'points.sqlite3';server.initialize()
   def account(name):
    r=Response('POST','/api/register',{'name':name,'password':'test-password-123'})
    cookie=r.headers['Set-Cookie'].split(';')[0]
    return cookie,Response('GET','/api/state',cookie=cookie).data['user']['id']
   alice,aid=account('Alice');bob,bid=account('Bob');private,pid=account('Private member')
   first=Response('POST','/api/checkin',{'event':'noah-kahan','points':999999},alice).data
   self.assertEqual(first['points_awarded'],100)
   repeat=Response('POST','/api/checkin',{'event':'noah-kahan'},alice).data
   self.assertEqual(repeat['points_awarded'],0);self.assertEqual(repeat['total_points'],100)
   Response('POST','/api/checkin',{'event':'olivia-rodrigo'},alice)
   Response('POST','/api/checkin',{'event':'noah-kahan'},bob)
   Response('POST','/api/checkin',{'event':'noah-kahan'},private)
   Response('POST','/api/privacy',{'visibility':'private'},private)
   self.assertEqual(Response('GET','/api/state',cookie=alice).data['points'],200)
   self.assertEqual(Response('GET','/api/leaderboards').data['entries'],[])
   self.assertEqual(Response('POST','/api/leaderboard-preference',{'enabled':True}).status,401)
   self.assertEqual(Response('POST','/api/leaderboard-preference',{'enabled':'yes'},alice).status,400)
   for cookie in [alice,bob]:Response('POST','/api/leaderboard-preference',{'enabled':True},cookie)
   board=Response('GET','/api/leaderboards').data
   self.assertEqual([p['id'] for p in board['entries']],[aid,bid]);self.assertEqual(board['entries'][0]['points'],200)
   self.assertNotIn(pid,[p['id'] for p in board['entries']])
   self.assertEqual(Response('GET','/api/leaderboards?scope=friends').status,401)
   self.assertEqual(len(Response('GET','/api/leaderboards?scope=friends',cookie=alice).data['entries']),1)
   Response('POST','/api/friend',{'user':bid,'action':'request'},alice);Response('POST','/api/friend',{'user':aid,'action':'accept'},bob)
   self.assertEqual(len(Response('GET','/api/leaderboards?scope=friends',cookie=alice).data['entries']),2)
   cutoff=server.datetime.now(server.ZoneInfo('America/New_York')).replace(day=1,hour=0,minute=0,second=0,microsecond=0).timestamp()
   with server.db() as c:c.execute('UPDATE attendance SET created=? WHERE user=? AND event=?',(cutoff-60,aid,'olivia-rodrigo'))
   monthly=Response('GET','/api/leaderboards?period=month').data['entries']
   self.assertEqual([p['points'] for p in monthly],[100,100]);self.assertEqual([p['rank'] for p in monthly],[1,1])
   self.assertEqual(Response('GET','/api/state',cookie=alice).data['points'],200)
   Response('POST','/api/leaderboard-preference',{'enabled':False},alice)
   self.assertNotIn(aid,[p['id'] for p in Response('GET','/api/leaderboards').data['entries']])
   server.initialize();self.assertEqual(Response('GET','/api/state',cookie=bob).data['points'],100)
 def test_log_photos_blurb_and_friends(self):
  with tempfile.TemporaryDirectory() as tmp:
   server.DB=Path(tmp)/'log-details.sqlite3';server.initialize()
   def account(name):
    cookie=Response('POST','/api/register',{'name':name,'password':'password-test-123'}).headers['Set-Cookie'].split(';')[0]
    return cookie,Response('GET','/api/state',cookie=cookie).data['user']['id']
   alice,aid=account('Alice');bob,bid=account('Bob');eve,eid=account('Eve')
   Response('POST','/api/friend',{'user':bid,'action':'request'},alice);Response('POST','/api/friend',{'user':aid,'action':'accept'},bob)
   pix='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=='
   show={'artist':'boygenius','venue':'Forest Hills Stadium','city':'Queens','date':'2023-07-01'}
   self.assertEqual(Response('POST','/api/concert-log',{**show,'friends':[eid]},alice).status,400)  # not a friend
   self.assertEqual(Response('POST','/api/concert-log',{**show,'blurb':'x'*2001},alice).status,400)
   self.assertEqual(Response('POST','/api/concert-log',{**show,'photos':['not a photo']},alice).status,400)
   r=Response('POST','/api/concert-log',{**show,'rating':4.5,'blurb':' Best night. ','friends':[bid],'photos':[pix,pix]},alice);self.assertEqual(r.status,200)
   log=Response('GET','/api/state',cookie=alice).data['concert_history'][0]
   self.assertEqual((log['rating'],log['blurb'],log['friends'],len(log['photos'])),(4.5,'Best night.',['Bob'],2))
   self.assertTrue(all(src.startswith('/api/media/feed/') for src in log['photos']))
   post=next(x for x in Response('GET','/api/feed').data if x['id']==log['photo_post'])
   self.assertEqual((post['artist'],post['city'],post['body']),('boygenius','Queens','Best night.'))
   # Saving again without the new fields keeps them; skipping photos keeps the earlier ones.
   self.assertEqual(Response('POST','/api/concert-log',show,alice).status,200)
   log=Response('GET','/api/state',cookie=alice).data['concert_history'][0]
   self.assertEqual((log['blurb'],log['friends'],len(log['photos'])),('Best night.',['Bob'],2))
   # Editing later: new photos join the same post, the caption follows the blurb, and the cap is 10.
   self.assertEqual(log['friend_ids'],[bid])
   self.assertEqual(Response('POST','/api/concert-log',{**show,'blurb':'Still thinking about it.','photos':[pix]},alice).status,200)
   log2=Response('GET','/api/state',cookie=alice).data['concert_history'][0]
   self.assertEqual((log2['photo_post'],len(log2['photos']),log2['blurb']),(log['photo_post'],3,'Still thinking about it.'))
   self.assertEqual(next(x for x in Response('GET','/api/feed').data if x['id']==log['photo_post'])['body'],'Still thinking about it.')
   self.assertEqual(Response('POST','/api/concert-log',{**show,'photos':[pix]*8},alice).status,400)
   # Polaroid background: only listed backgrounds are accepted, and it is saved on the photo post.
   from unittest.mock import patch
   self.assertEqual(Response('POST','/api/concert-log',{**show,'backdrop':'nope'},alice).status,400)
   with patch.object(server,'backdrops',return_value=[{'id':'disco-balls','name':'Disco balls','url':'/backdrops/disco-balls.jpg'}]):
    self.assertEqual(Response('POST','/api/concert-log',{**show,'backdrop':'disco-balls'},alice).status,200)
    self.assertEqual(Response('GET','/api/state',cookie=alice).data['concert_history'][0]['backdrop'],'disco-balls')
    self.assertEqual(next(x for x in Response('GET','/api/feed').data if x['id']==log['photo_post'])['backdrop'],'disco-balls')
    self.assertEqual(Response('POST','/api/feed-post',{'photos':[pix],'backdrop':'disco-balls'},bob).status,200)
    self.assertEqual(Response('POST','/api/feed-post',{'photos':[pix],'backdrop':'../etc'},bob).status,400)
 def test_moderation(self):
  from unittest.mock import patch
  with tempfile.TemporaryDirectory() as tmp:
   server.DB=Path(tmp)/'mod.sqlite3';server.initialize()
   def account(name):
    response=Response('POST','/api/register',{'name':name,'password':'password-test-123'})
    cookie=response.headers['Set-Cookie'].split(';')[0]
    return cookie,Response('GET','/api/state',cookie=cookie).data['user']['id']
   alice,aid=account('Alice');troll,tid=account('Troll');mod,mid=account('Mod')
   # accounts made before this feature (created is NULL) count as established
   with server.db() as c:c.execute('UPDATE users SET created=NULL')
   with patch.dict(server.os.environ,{'ADMIN_USERNAMES':'@Mod_fan, nobody'}):server.initialize()
   self.assertEqual(Response('GET','/api/state',cookie=mod).data['user']['is_admin'],1)
   self.assertEqual(Response('GET','/api/state',cookie=alice).data['user']['is_admin'],0)
   cid=Response('GET','/api/communities').data[0]['id']
   for who in (alice,troll):Response('POST','/api/community-join',{'community':cid},who)
   self.assertEqual(Response('POST','/api/community-message',{'community':cid,'body':'you are awful'},troll).status,200)
   msg=Response('GET','/api/community/'+cid,cookie=alice).data['messages'][0]['id']
   # reports: validated, one per person per item, never your own
   self.assertEqual(Response('POST','/api/report',{'target_type':'message','target_id':msg,'reason':'harassment'}).status,401)
   self.assertEqual(Response('POST','/api/report',{'target_type':'message','target_id':msg,'reason':'meh'},alice).status,400)
   self.assertEqual(Response('POST','/api/report',{'target_type':'nope','target_id':msg,'reason':'spam'},alice).status,400)
   self.assertEqual(Response('POST','/api/report',{'target_type':'message','target_id':'missing','reason':'spam'},alice).status,404)
   self.assertEqual(Response('POST','/api/report',{'target_type':'message','target_id':msg,'reason':'spam'},troll).status,400)
   for _ in range(2):self.assertEqual(Response('POST','/api/report',{'target_type':'message','target_id':msg,'reason':'harassment','note':'rude'},alice).status,200)
   self.assertEqual(Response('POST','/api/report',{'target_type':'user','target_id':tid,'reason':'harassment'},alice).status,200)
   # only admins see the queue
   self.assertEqual(Response('GET','/api/admin/reports',cookie=alice).status,403)
   self.assertEqual(Response('GET','/api/admin/reports').status,403)
   queue=Response('GET','/api/admin/reports',cookie=mod).data['items']
   item=next(g for g in queue if g['target_type']=='message');self.assertEqual(item['reports'],1);self.assertEqual(item['text'],'you are awful');self.assertEqual(item['author']['id'],tid);self.assertEqual(item['reasons'][0]['note'],'rude')
   self.assertEqual(Response('POST','/api/admin/action',{'action':'hide','target_type':'message','target_id':msg},alice).status,403)
   # hiding removes it for everyone and closes its reports; unhiding brings it back
   self.assertEqual(Response('POST','/api/admin/action',{'action':'hide','target_type':'message','target_id':msg},mod).status,200)
   self.assertEqual(Response('GET','/api/community/'+cid,cookie=alice).data['messages'],[])
   self.assertFalse(any(g['target_type']=='message' for g in Response('GET','/api/admin/reports',cookie=mod).data['items']))
   self.assertTrue(any(g['target_id']==msg and g['hidden'] for g in Response('GET','/api/admin/reports?status=closed',cookie=mod).data['items']))
   self.assertEqual(Response('POST','/api/admin/action',{'action':'unhide','target_type':'message','target_id':msg},mod).status,200)
   self.assertEqual(len(Response('GET','/api/community/'+cid,cookie=alice).data['messages']),1)
   # blocking hides each other's messages and profiles, ends friendships, stops requests
   Response('POST','/api/friend',{'user':tid,'action':'request'},alice)
   self.assertEqual(Response('POST','/api/block',{'user':aid,'blocked':True},alice).status,400)
   self.assertEqual(Response('POST','/api/block',{'user':tid,'blocked':True},alice).status,200)
   self.assertEqual(Response('GET','/api/community/'+cid,cookie=alice).data['messages'],[])
   self.assertEqual(len(Response('GET','/api/community/'+cid,cookie=mod).data['messages']),1)
   self.assertTrue(Response('GET','/api/profile/'+tid,cookie=alice).data['blocked'])
   self.assertFalse(Response('GET','/api/profile/'+aid,cookie=troll).data['can_view'])
   self.assertFalse(Response('GET','/api/profile/'+aid,cookie=troll).data['blocked'])   # they aren't told they were blocked
   self.assertEqual(Response('POST','/api/friend',{'user':aid,'action':'request'},troll).status,403)
   self.assertNotIn(tid,[p['id'] for p in Response('GET','/api/people',cookie=alice).data])
   self.assertEqual(Response('GET','/api/profile/'+tid,cookie=alice).data['relationship'],'none')   # the pending request was cleared
   self.assertEqual(Response('POST','/api/block',{'user':tid,'blocked':False},alice).status,200)
   self.assertEqual(len(Response('GET','/api/community/'+cid,cookie=alice).data['messages']),1)
   # banning signs them out, blocks sign-in, hides their posts, and can be undone
   self.assertEqual(Response('POST','/api/admin/action',{'action':'ban','target_type':'user','target_id':mid},mod).status,400)
   self.assertEqual(Response('POST','/api/admin/action',{'action':'ban','target_type':'message','target_id':msg},mod).status,200)
   self.assertIsNone(Response('GET','/api/state',cookie=troll).data['user'])
   self.assertEqual(Response('POST','/api/login',{'username':'troll_fan','password':'password-test-123'}).status,403)
   self.assertEqual(Response('GET','/api/community/'+cid,cookie=alice).data['messages'],[])
   self.assertEqual(Response('GET','/api/profile/'+tid,cookie=alice).status,404)
   self.assertFalse(any(g['target_type']=='message' for g in Response('GET','/api/admin/reports',cookie=mod).data['items']))
   self.assertEqual(Response('POST','/api/admin/action',{'action':'unban','target_type':'user','target_id':tid},mod).status,200)
   self.assertEqual(Response('POST','/api/login',{'username':'troll_fan','password':'password-test-123'}).status,200)
   with server.db() as c:
    self.assertEqual([r['action'] for r in c.execute('SELECT action FROM mod_actions ORDER BY created')],['hide','unhide','ban','unban'])
 def test_posting_limits(self):
  with tempfile.TemporaryDirectory() as tmp:
   server.DB=Path(tmp)/'limits.sqlite3';server.initialize()
   cookie=Response('POST','/api/register',{'name':'Newbie','password':'password-test-123'}).headers['Set-Cookie'].split(';')[0]
   cid=Response('GET','/api/communities').data[0]['id'];Response('POST','/api/community-join',{'community':cid},cookie)
   # brand-new accounts can't post links on day one
   self.assertEqual(Response('POST','/api/community-message',{'community':cid,'body':'cheap tix at scam.com'},cookie).status,429)
   self.assertEqual(Response('POST','/api/community-message',{'community':cid,'body':'see https://x.io'},cookie).status,429)
   # and they can send 8 messages a minute
   for i in range(8):self.assertEqual(Response('POST','/api/community-message',{'community':cid,'body':f'hi {i}'},cookie).status,200)
   self.assertEqual(Response('POST','/api/community-message',{'community':cid,'body':'one more'},cookie).status,429)
   with server.db() as c:c.execute('UPDATE users SET created=?',(server.time.time()-2*86400,))
   self.assertEqual(Response('POST','/api/community-message',{'community':cid,'body':'tickets at https://example.com'},cookie).status,200)
if __name__=='__main__':unittest.main()
