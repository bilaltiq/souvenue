"""Screenshots and rendered-design measurements for /design-review (Souvenue).

Drives the installed Google Chrome over the DevTools protocol with only the
standard library (this Mac has no node, playwright or websocket package).

  python3 .claude/skills/design-review/shot.py --pages / /artists --widths 1280,390
  python3 .claude/skills/design-review/shot.py --pages /event/noah-kahan --signin --checkin
  python3 .claude/skills/design-review/shot.py --pages /artists --tag after   # after a fix

Writes PNGs plus measure.json (fonts, colours, type sizes, radii, outlined boxes,
small tap targets, console errors) into .design-review/<date>/.
Point --base at a server running a COPY of the database (see SKILL.md), never demo.sqlite3.
"""
import argparse, base64, json, os, socket, struct, subprocess, tempfile, time, urllib.request
from datetime import date
from pathlib import Path

CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
ROOT = Path(__file__).resolve().parents[3]


class Tab:
    def __init__(self, port):
        self.dir = tempfile.mkdtemp(prefix='souv-review-')
        self.proc = subprocess.Popen([CHROME, '--headless', '--disable-gpu', '--hide-scrollbars', f'--remote-debugging-port={port}',
                                      f'--user-data-dir={self.dir}', 'about:blank'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(60):
            try:
                url = next(t['webSocketDebuggerUrl'] for t in json.load(urllib.request.urlopen(f'http://127.0.0.1:{port}/json')) if t['type'] == 'page')
                break
            except Exception:
                time.sleep(0.2)
        else:
            raise SystemExit(f'Chrome did not start on port {port}. Try another --port, or: pkill -f remote-debugging-port=94')
        host, rest = url[5:].split('/', 1); h, p = host.split(':')
        self.s = socket.create_connection((h, int(p)))
        self.s.send(f'GET /{rest} HTTP/1.1\r\nHost: {host}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n'
                    f'Sec-WebSocket-Key: {base64.b64encode(os.urandom(16)).decode()}\r\nSec-WebSocket-Version: 13\r\n\r\n'.encode())
        buf = b''
        while b'\r\n\r\n' not in buf: buf += self.s.recv(1)
        self.i, self.errors = 0, []
        self.call('Runtime.enable'); self.call('Log.enable')

    def _send(self, data):
        b = json.dumps(data).encode(); m = os.urandom(4); n = len(b)
        head = bytes([0x81]) + (bytes([0x80 | n]) if n < 126 else bytes([0xfe]) + struct.pack('>H', n) if n < 65536 else bytes([0xff]) + struct.pack('>Q', n))
        self.s.sendall(head + m + bytes(c ^ m[i % 4] for i, c in enumerate(b)))

    def _rx(self, n):
        b = b''
        while len(b) < n: b += self.s.recv(n - len(b))
        return b

    def _recv(self):
        data = b''
        while True:
            h = self._rx(2); n = h[1] & 0x7f
            if n == 126: n = struct.unpack('>H', self._rx(2))[0]
            elif n == 127: n = struct.unpack('>Q', self._rx(8))[0]
            data += self._rx(n)
            if h[0] & 0x80: return json.loads(data)

    def call(self, method, **params):
        self.i += 1; self._send({'id': self.i, 'method': method, 'params': params})
        while True:
            r = self._recv()
            if r.get('method') == 'Runtime.exceptionThrown':
                self.errors.append(r['params']['exceptionDetails'].get('exception', {}).get('description', 'exception')[:300])
            elif r.get('method') == 'Runtime.consoleAPICalled' and r['params'].get('type') == 'error':
                self.errors.append(' '.join(str(a.get('value', a.get('description', ''))) for a in r['params']['args'])[:300])
            elif r.get('method') == 'Log.entryAdded' and r['params']['entry'].get('level') == 'error':
                self.errors.append(r['params']['entry'].get('text', '')[:300])
            if r.get('id') == self.i: return r.get('result', r)

    def js(self, expr):
        r = self.call('Runtime.evaluate', expression=expr, returnByValue=True, awaitPromise=True)
        return r.get('result', {}).get('value', r)

    def open(self, url, width, height=900, wait=3.5):
        # A real viewport at any width (window-size cannot go below ~500px on macOS).
        self.call('Emulation.setDeviceMetricsOverride', width=width, height=height, deviceScaleFactor=1, mobile=width < 500)
        self.call('Page.navigate', url=url); time.sleep(wait)

    def shot(self, path, full=True):
        if full:
            h = int(self.js('Math.min(document.documentElement.scrollHeight, 9000)') or 900)
            w = int(self.js('window.innerWidth'))
            self.call('Emulation.setDeviceMetricsOverride', width=w, height=h, deviceScaleFactor=1, mobile=w < 500); time.sleep(0.8)
        path.write_bytes(base64.b64decode(self.call('Page.captureScreenshot', format='png')['data']))

    def close(self):
        self.proc.kill()


# Measures what is rendered, not what the CSS intends.
MEASURE = r"""(() => {
 const els = [...document.querySelectorAll('#app *, header *')].filter(e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; });
 const count = list => Object.entries(list.reduce((m, v) => (m[v] = (m[v] || 0) + 1, m), {})).sort((a, b) => b[1] - a[1]);
 const cs = els.map(e => [e, getComputedStyle(e)]);
 const label = e => (e.tagName.toLowerCase() + (e.id ? '#' + e.id : '') + (typeof e.className === 'string' && e.className ? '.' + e.className.trim().split(/\s+/).slice(0, 2).join('.') : '') + ' "' + (e.textContent || e.value || '').trim().slice(0, 28) + '"');
 const textEls = cs.filter(([e]) => [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim()));
 return {
  url: location.pathname, width: innerWidth, layoutWidth: document.documentElement.scrollWidth,
  widestElements: innerWidth < 500 ? [...document.querySelectorAll('#app *')].map(e => [e, e.getBoundingClientRect()]).filter(([, r]) => r.right > Math.min(innerWidth, screen.width) + 1).sort((x, y) => y[1].right - x[1].right).slice(0, 5).map(([e, r]) => (e.tagName.toLowerCase() + '.' + (typeof e.className === 'string' ? e.className.split(' ')[0] : '')) + ' right=' + Math.round(r.right)) : [],
  fonts: count(textEls.map(([, s]) => s.fontFamily.split(',')[0].replace(/["']/g, ''))),
  fontSizes: count(textEls.map(([, s]) => s.fontSize)),
  tooSmallText: textEls.filter(([, s]) => parseFloat(s.fontSize) < 12).map(([e, s]) => label(e) + ' ' + s.fontSize).slice(0, 15),
  colors: count(textEls.map(([, s]) => s.color)).slice(0, 20),
  backgrounds: count(cs.map(([, s]) => s.backgroundColor).filter(c => c !== 'rgba(0, 0, 0, 0)')).slice(0, 20),
  headings: [...document.querySelectorAll('h1,h2,h3,h4')].filter(h => h.offsetParent).map(h => [h.tagName, getComputedStyle(h).fontSize, getComputedStyle(h).fontWeight, h.textContent.trim().slice(0, 40)]),
  radii: count(cs.map(([, s]) => s.borderTopLeftRadius).filter(r => r !== '0px')).slice(0, 15),
  outlinedBoxes: cs.filter(([e, s]) => ['Top', 'Right', 'Bottom', 'Left'].filter(k => { const c = s['border' + k + 'Color'], alpha = /rgba\(.*, ([\d.]+)\)$/.exec(c); return parseFloat(s['border' + k + 'Width']) > 0 && s['border' + k + 'Style'] !== 'none' && c !== s.backgroundColor && !(alpha && parseFloat(alpha[1]) < 0.25); }).length >= 3 && e.getBoundingClientRect().width > 120)
   .map(([e, s]) => label(e) + ' border ' + s.borderTopWidth + ' ' + s.borderTopColor + ' radius ' + s.borderTopLeftRadius).slice(0, 25),
  dividerRules: cs.filter(([e, s]) => (parseFloat(s.borderBottomWidth) > 0 || parseFloat(s.borderTopWidth) > 0) && e.getBoundingClientRect().width > 300 && parseFloat(s.borderLeftWidth) === 0).length,
  smallTapTargets: [...document.querySelectorAll('#app a, #app button, #app input, #app select, header a, header button')].filter(e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && (r.height < 44 || r.width < 44); }).map(e => { const r = e.getBoundingClientRect(); return label(e) + ' ' + Math.round(r.width) + 'x' + Math.round(r.height); }).slice(0, 20),
  uppercaseLabels: textEls.filter(([, s]) => s.textTransform === 'uppercase' && parseFloat(s.letterSpacing) > 0.5).map(([e]) => label(e)).slice(0, 10),
  textGlyphIcons: textEls.filter(([e]) => /^[★☆✓✔＋+→←✕×♥❤️✨🎉🎶🎤]\s?$/u.test((e.textContent || '').trim().slice(0, 2))).map(([e]) => label(e)).slice(0, 10),
  horizontalScroll: document.documentElement.scrollWidth > Math.min(innerWidth, screen.width) + 1,
  imagesWithoutAlt: [...document.querySelectorAll('img:not([alt])')].length,
 };
})()"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://127.0.0.1:4174')
    ap.add_argument('--pages', nargs='+', default=['/', '/artists', '/artist/olivia-rodrigo', '/log', '/communities', '/leaderboards'])
    ap.add_argument('--widths', default='1280,390')
    ap.add_argument('--out', default=str(ROOT / '.design-review' / date.today().isoformat()))
    ap.add_argument('--tag', default='', help='suffix for file names, e.g. before / after / finding-003-after')
    ap.add_argument('--signin', action='store_true', help='register or sign in a throwaway "Design Review" account first')
    ap.add_argument('--checkin', action='store_true', help='with --signin: check in to each /event/ page via its demo tap link')
    ap.add_argument('--no-measure', action='store_true')
    ap.add_argument('--port', type=int, default=9400 + os.getpid() % 90)
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    tab = Tab(a.port); report = []
    try:
        if a.signin:
            tab.open(a.base + '/', 1280, wait=2)
            body = json.dumps({'name': 'Design Review', 'password': 'design-review-123'})
            tab.js(f"fetch('/api/register',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:{json.dumps(body)}}}).then(r=>r.ok||fetch('/api/login',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:{json.dumps(body)}}}))")
        for page in a.pages:
            if a.checkin and page.startswith('/event/'):
                tab.open(a.base + '/tap/' + page.split('/')[2], 1280, wait=4)
            for w in [int(x) for x in a.widths.split(',')]:
                tab.errors = []
                tab.open(a.base + page, w)
                name = (page.strip('/').replace('/', '-') or 'home') + f'-{w}' + (f'-{a.tag}' if a.tag else '')
                if not a.no_measure:
                    m = tab.js(MEASURE)
                    if isinstance(m, dict): m['consoleErrors'] = tab.errors[:]; report.append(m)
                tab.shot(out / f'{name}.png')
                print(out / f'{name}.png')
    finally:
        tab.close()
    if report:
        path = out / ('measure' + (f'-{a.tag}' if a.tag else '') + '.json')
        path.write_text(json.dumps(report, indent=1, ensure_ascii=False))
        print(path)


if __name__ == '__main__':
    main()
