"""Draws each artist's crayon mark: a small symbol that stands for them, coloured in
like a crayon drawing (scribbled fill, wobbly outline, waxy grain). Writes
public/marks/<slug>.svg. Run: python3 scripts/crayon_marks.py"""
import math, random, pathlib, hashlib

OUT = pathlib.Path(__file__).resolve().parent.parent / 'public' / 'marks'
PINK, HOT, RED, BLUE, SKY, LILAC, PURPLE, MINT, PERI, BUTTER, PEACH, WHITE, LIME, GREEN, DARK, TAN = (
  '#ff9fd6', '#ff74cb', '#ff7a9c', '#9ed9ff', '#70caff', '#cdb4ff', '#b48cff', '#a8ecd0', '#b5c7ff',
  '#ffe7a0', '#ffbe9a', '#f4f2ff', '#c6f26b', '#7fdca4', '#191b33', '#d9a77c')

# ---- shape helpers (200 x 200 canvas) ----
def circle(cx, cy, r): return f'M{cx-r},{cy}a{r},{r} 0 1,0 {2*r},0a{r},{r} 0 1,0 {-2*r},0Z'
def ellipse(cx, cy, rx, ry, rot=0, n=36):
  a = math.radians(rot); pts = []
  for i in range(n):
    t = 2*math.pi*i/n; x, y = rx*math.cos(t), ry*math.sin(t)
    pts.append((cx + x*math.cos(a) - y*math.sin(a), cy + x*math.sin(a) + y*math.cos(a)))
  return poly(pts)
def poly(pts): return 'M' + 'L'.join(f'{x:.1f},{y:.1f}' for x, y in pts) + 'Z'
def rect(x, y, w, h, r=0):
  return f'M{x+r},{y}H{x+w-r}Q{x+w},{y} {x+w},{y+r}V{y+h-r}Q{x+w},{y+h} {x+w-r},{y+h}H{x+r}Q{x},{y+h} {x},{y+h-r}V{y+r}Q{x},{y} {x+r},{y}Z'
def star(cx, cy, R, r, n=5, rot=-90):
  return poly([(cx + (R if i % 2 == 0 else r)*math.cos(math.radians(rot + i*180/n)),
                cy + (R if i % 2 == 0 else r)*math.sin(math.radians(rot + i*180/n))) for i in range(2*n)])
def heart(cx, cy, s):  # s = half width
  k = s/70
  P = lambda x, y: f'{cx + x*k:.1f},{cy + y*k:.1f}'
  return f'M{P(0,62)}C{P(-60,20)} {P(-80,-10)} {P(-68,-38)}C{P(-56,-66)} {P(-14,-66)} {P(0,-34)}C{P(14,-66)} {P(56,-66)} {P(68,-38)}C{P(80,-10)} {P(60,20)} {P(0,62)}Z'
def sector(cx, cy, r1, r2, a0, a1):
  p = lambda r, a: (cx + r*math.cos(math.radians(a)), cy + r*math.sin(math.radians(a)))
  (x1, y1), (x2, y2), (x3, y3), (x4, y4) = p(r2, a0), p(r2, a1), p(r1, a1), p(r1, a0)
  return f'M{x1:.1f},{y1:.1f}A{r2},{r2} 0 0,1 {x2:.1f},{y2:.1f}L{x3:.1f},{y3:.1f}A{r1},{r1} 0 0,0 {x4:.1f},{y4:.1f}Z'
def mirror(pts): return pts + [(200 - x, y) for x, y in reversed(pts)]

F = lambda d, c, **k: ('fill', d, c, k)       # coloured-in shape
L = lambda d, c, w=7, **k: ('line', d, c, dict(k, w=w))  # crayon line

def bee():
  body = ellipse(100, 112, 46, 34)
  return [F(ellipse(78, 72, 22, 30, -25), WHITE, light=True), F(ellipse(122, 72, 22, 30, 25), WHITE, light=True),
          F(body, BUTTER), F(rect(84, 70, 13, 90), DARK, clip=body), F(rect(110, 70, 13, 90), DARK, clip=body),
          L('M146,112 L160,114', DARK, 6), L('M64,100 C52,84 50,72 56,64', DARK, 5), L('M70,96 C66,78 70,66 78,60', DARK, 5)]

def flower_ring():
  parts = []
  for i in range(8):
    a = math.radians(-90 + i*45); x, y = 100 + 55*math.cos(a), 100 + 55*math.sin(a)
    parts.append(F(ellipse(100 + 55*math.cos(a + .39), 100 + 55*math.sin(a + .39), 12, 6, math.degrees(a) + 90), GREEN))
    for j in range(5):
      b = math.radians(j*72 + i*20)
      parts.append(F(circle(round(x + 9*math.cos(b), 1), round(y + 9*math.sin(b), 1), 8), [PINK, LILAC, BLUE, PEACH][i % 4]))
    parts.append(F(circle(round(x, 1), round(y, 1), 5), BUTTER))
  return parts

def sunflower():
  parts = [F(ellipse(100 + 44*math.cos(math.radians(a)), 100 + 44*math.sin(math.radians(a)), 22, 10, a), BUTTER) for a in range(0, 360, 30)]
  return parts + [F(circle(100, 100, 28), TAN), L('M88,92 L112,116 M112,92 L88,116 M100,84 L100,120', '#9b6c4a', 4)]

def snowflake():
  parts = []
  for a in range(0, 180, 60):
    r = math.radians(a); dx, dy = 68*math.cos(r), 68*math.sin(r)
    parts.append(L(f'M{100-dx:.1f},{100-dy:.1f} L{100+dx:.1f},{100+dy:.1f}', BLUE, 8))
  for a in range(0, 360, 60):
    r = math.radians(a)
    for d, s in ((42, 16), (62, 11)):
      cx, cy = 100 + d*math.cos(r), 100 + d*math.sin(r)
      for o in (-1, 1):
        q = r + o*math.radians(50) + math.pi
        parts.append(L(f'M{cx:.1f},{cy:.1f} L{cx + s*math.cos(q - math.pi*0 ):.1f},{cy + s*math.sin(q):.1f}', WHITE, 6))
  return parts

def spiral():
  pts = [(100 + 4.2*t*math.cos(t), 100 + 4.2*t*math.sin(t)) for t in [i*0.2 for i in range(2, 85)]]
  pts2 = [(100 + 4.2*t*math.cos(t + math.pi), 100 + 4.2*t*math.sin(t + math.pi)) for t in [i*0.2 for i in range(2, 80)]]
  path = lambda p: 'M' + 'L'.join(f'{x:.1f},{y:.1f}' for x, y in p)
  return [L(path(pts), PURPLE, 9), L(path(pts2), PINK, 7)]

def waveform():
  out = []
  for i, x in enumerate(range(28, 176, 10)):
    u = (x - 100)/72
    h = 10 + 58*abs(math.sin(u*math.pi*1.05))*(1 - .45*u*u) + (8 if i % 2 else 0)
    out.append(L(f'M{x},{100-h/2:.0f} L{x},{100+h/2:.0f}', WHITE if i % 3 else LILAC, 6))
  return out

def globe():
  g = circle(100, 100, 60)
  return [F(g, BLUE), F(poly([(62,72),(88,62),(98,80),(84,96),(90,118),(74,124),(66,100)]), GREEN, clip=g),
          F(poly([(108,88),(140,76),(156,98),(140,130),(118,140),(112,112)]), GREEN, clip=g),
          L('M40,100 L160,100 M100,40 C70,70 70,130 100,160 M100,40 C130,70 130,130 100,160', WHITE, 3)]

def leaf():
  half = [(100,24),(112,54),(130,44),(124,82),(154,62),(149,88),(176,96),(144,118),(152,134),(112,126),(104,150)]
  return [F(poly(mirror(half)), PEACH), L('M100,140 L100,178', TAN, 7), L('M100,60 L100,140 M100,110 L130,92 M100,110 L70,92', '#e58f6a', 3)]

def disco():
  b = circle(100, 108, 56)
  lines = ''.join(f'M44,{y} L156,{y} ' for y in range(70, 160, 14)) + ''.join(f'M{x},50 C{x + (x-100)*.35:.0f},90 {x + (x-100)*.35:.0f},130 {x},166 ' for x in range(58, 150, 14))
  return [L('M100,52 L100,18', WHITE, 4), F(b, PERI), ('line', lines, WHITE, dict(w=2.5, clip=b)),
          F(star(156, 54, 14, 5, 4), WHITE), F(star(44, 160, 10, 4, 4), PINK)]

def daisy():
  petals = [F(ellipse(100 + 31*math.cos(math.radians(a)), 80 + 31*math.sin(math.radians(a)), 22, 7.5, a), WHITE, opaque=True, light=True) for a in range(0, 360, 24)]
  return ([L('M100,104 C97,130 104,152 100,184', MINT, 7), F('M101,152 C116,132 140,130 150,138 C136,154 118,158 101,152Z', MINT)] +
          petals + [F(circle(100, 80, 15), BUTTER, opaque=True)])

def tube(d, w, cap=None):  # a vessel: ink outline with the inside left open, plus an open ring at the end
  out = [L(d, DARK, w + 9), L(d, RED, w, knock=True, thin=True)]
  if cap: out.append(L(ellipse(*cap), DARK, 4.5))
  return out

def anatomical_heart():
  return (tube('M80,92 L78,40', 13, (78, 38, 9, 3.5)) +
          tube('M106,90 C104,52 114,36 134,36 C152,36 160,50 160,72', 15, (160, 74, 9, 3.5)) +
          tube('M120,42 L116,20', 7, (116, 18, 5, 2.2)) + tube('M134,37 L135,16', 7, (135, 14, 5, 2.2)) + tube('M147,42 L153,22', 7, (153, 20, 5, 2.2)) +
          [F('M64,90 C46,102 42,134 56,156 C68,174 82,186 94,188 C102,188 110,180 120,172 C144,154 160,126 154,100 C150,84 134,78 120,84 C106,76 82,76 64,90Z', RED, opaque=True)] +
          tube('M100,100 C84,86 66,82 46,84', 12, (44, 84, 3.5, 8.5)) +
          [L('M112,100 C104,124 108,146 96,176 M106,134 C122,138 132,148 138,160 M70,112 C64,126 66,140 72,152', DARK, 3.5)])

def guitar():  # electric guitar, drawn upright then tilted
  t = dict(tf='rotate(32 100 100)')
  return [F('M92,32 L90,12 C94,6 110,6 112,12 L108,32Z', RED, **t), F(rect(93, 30, 14, 76, 3), RED, **t),
          L('M88,16 L84,16 M88,24 L84,24 M112,16 L116,16 M112,24 L116,24', DARK, 4, **t),
          F('M74,114 C62,102 58,92 66,86 C74,80 82,92 90,102 L110,102 C116,88 126,78 136,84 C144,90 138,104 128,116 C142,126 146,148 132,164 C120,178 80,178 68,164 C56,150 60,126 74,114Z', RED, **t),
          F(rect(86, 112, 28, 8, 3), DARK, **t), F(rect(86, 130, 28, 8, 3), DARK, **t), F(rect(88, 152, 24, 6, 2), WHITE, **t),
          F(circle(126, 150, 5), DARK, **t), F(circle(118, 162, 5), DARK, **t), L('M96,34 L96,154 M100,34 L100,154 M104,34 L104,154', WHITE, 1.6, thin=True, **t),
          L('M134,124 C150,132 156,146 150,156', DARK, 4, **t)]

def sneaker():
  return [F('M30,140 L30,108 C30,96 44,92 56,92 L80,70 L112,74 C120,96 140,104 166,112 C178,116 180,130 176,140Z', WHITE),
          F(rect(24, 138, 156, 18, 9), PINK), F('M150,108 C166,112 178,118 178,138 L140,138 C140,124 142,112 150,108Z', BLUE),
          L('M84,82 L104,98 M78,90 L98,106 M72,98 L92,114', DARK, 4)]

SYMBOLS = {
 'arctic-monkeys': waveform,
 'ariana-grande': lambda: [F('M100,96 C70,58 32,62 36,94 C40,126 74,120 100,100Z', LILAC), F('M100,96 C130,58 168,62 164,94 C160,126 126,120 100,100Z', LILAC),
                           L('M94,104 L72,164', LILAC, 10), L('M106,104 L128,164', LILAC, 10), F(circle(100, 99, 13), PINK)],
 'bad-bunny': lambda: [F(heart(100, 104, 72), RED), L('M58,78 C62,66 72,60 82,60', WHITE, 6)],
 'beabadoobee': lambda: [F(rect(52, 82, 80, 84, 12), BLUE), L('M132,100 C166,98 166,148 132,146', BLUE, 11),
                         L('M74,68 C64,56 86,48 76,34 M100,68 C90,56 112,48 102,34', WHITE, 5), F(heart(92, 124, 18), PINK)],
 'billie-eilish': lambda: [F(circle(100, 52, 20), LIME), L('M100,74 L100,128', LIME, 10), L('M54,112 L100,88 L146,112', LIME, 10),
                           L('M100,128 L70,170 M100,128 L130,170', LIME, 10)],
 'blackpink': lambda: [L('M100,112 L100,174', WHITE, 14), F(rect(38, 52, 124, 62, 30), PINK), F(heart(100, 84, 22), HOT)],
 'bleachers': lambda: [F(poly([(26,168),(26,140),(62,140),(62,114),(98,114),(98,88),(134,88),(134,62),(172,62),(172,168)]), BLUE),
                       L('M152,62 L152,24', WHITE, 5), F(poly([(152,24),(180,32),(152,42)]), PINK)],
 'bts': lambda: [F(poly([(42,40),(92,62),(92,138),(42,160)]), PURPLE), F(poly([(158,40),(108,62),(108,138),(158,160)]), PURPLE)],
 'chappell-roan': lambda: [F('M62,126 C58,92 66,62 82,60 C92,58 96,72 100,72 C104,72 108,58 118,60 C134,62 142,92 138,126Z', PINK),
                           F('M18,114 C40,152 160,152 182,114 C164,128 140,134 100,134 C60,134 36,128 18,114Z', HOT), L('M64,112 C88,120 112,120 136,112', WHITE, 5),
                           F(star(156, 52, 14, 6), WHITE)],
 'charli-xcx': lambda: [F(rect(26, 52, 148, 96, 3), LIME),
                        L('M50,74 L50,126 M88,100 L88,126 M88,111 C90,101 100,98 108,102 M134,101 L134,126 M152,82 L152,121 C152,126 157,127 162,124 M144,98 L162,98', DARK, 5),
                        L(circle(63, 114, 12), DARK, 5), L(circle(122, 114, 11), DARK, 5)],
 'clairo': lambda: [L('M106,118 C116,146 122,162 140,174', GREEN, 8)] + [F(heart(x, y, 26).replace('', ''), MINT) for x, y in ()] +
                   [F(circle(80, 80, 25), MINT), F(circle(120, 80, 25), GREEN), F(circle(80, 120, 25), GREEN), F(circle(120, 120, 25), MINT)],
 'coldplay': lambda: [F(star(100, 106, 76, 32), BUTTER), F(star(160, 42, 12, 5), WHITE), F(star(38, 50, 8, 3), WHITE)],
 'conan-gray': lambda: [F('M148,34 C104,46 70,96 62,156 C96,144 146,100 148,34Z', PERI), L('M156,26 L54,172', WHITE, 5),
                        L('M128,64 L104,60 M118,84 L92,82 M106,106 L82,106 M94,126 L74,128', DARK, 3)],
 'doja-cat': lambda: [F('M48,84 L52,36 L84,64 C94,61 106,61 116,64 L148,36 L152,84 C162,118 142,160 100,160 C58,160 38,118 48,84Z', PINK),
                      F(ellipse(80, 104, 9, 12), DARK), F(ellipse(120, 104, 9, 12), DARK), F(heart(100, 126, 9), HOT),
                      L('M88,132 L44,124 M88,138 L46,144 M112,132 L156,124 M112,138 L154,144', WHITE, 3)],
 'dominic-fike': lambda: [L('M108,176 C98,146 96,112 104,80', PEACH, 13)] + [F(p, c) for p, c in (
                          ('M104,80 C84,52 56,50 34,66 C62,62 84,68 104,80Z', MINT), ('M104,80 C124,52 152,50 172,66 C144,62 124,68 104,80Z', GREEN),
                          ('M104,80 C86,72 56,82 46,108 C66,92 86,86 104,80Z', GREEN), ('M104,80 C122,72 152,82 162,108 C142,92 122,86 104,80Z', MINT),
                          ('M104,80 C98,56 106,36 124,26 C114,46 110,62 104,80Z', MINT))] + [F(circle(98, 86, 7), TAN), F(circle(112, 88, 7), TAN)],
 'dua-lipa': disco,
 'ed-sheeran': lambda: [L('M44,66 L88,66 M66,44 L66,88', PEACH, 10), L('M112,66 L156,66', BLUE, 10), F(circle(134, 48, 6), BLUE), F(circle(134, 84, 6), BLUE),
                        L('M48,116 L84,152 M84,116 L48,152', PINK, 10), L('M112,124 L156,124 M112,144 L156,144', MINT, 10)],
 'ethel-cain': lambda: [F(rect(78, 86, 44, 84, 5), WHITE), F('M100,32 C118,56 118,74 100,80 C82,74 82,56 100,32Z', BUTTER),
                        F('M100,52 C108,64 108,72 100,76 C92,72 92,64 100,52Z', PEACH), L('M100,80 L100,88', DARK, 4), L('M88,88 C88,100 92,106 92,112', LILAC, 5)],
 'florence-the-machine': flower_ring,
 'gracie-abrams': lambda: [L('M42,22 C58,82 86,96 100,98 M158,22 C142,82 114,96 100,98', BUTTER, 4), F(heart(100, 132, 46), LILAC), L(heart(100, 132, 28), WHITE, 3)],
 'harry-styles': lambda: [F('M38,128 Q100,168 162,128 L168,142 Q100,192 32,142Z', GREEN), F('M100,28 L40,130 Q100,166 160,130Z', PINK)] +
                         [F(ellipse(x, y, 4, 7, r), DARK) for x, y, r in ((100,72,0),(86,100,-12),(114,100,12),(72,124,-18),(100,128,0),(128,124,18))],
 'hayley-williams': lambda: [F(poly([(118,22),(58,112),(96,112),(80,178),(146,84),(108,84)]), PEACH)],
 'hozier': daisy,
 'julien-baker': lambda: [F('M100,34 C70,34 54,58 58,84 C62,104 80,112 82,128 L118,128 C120,112 138,104 142,84 C146,58 130,34 100,34Z', BUTTER),
                          F(rect(82, 132, 36, 26, 6), PERI), L('M84,141 L116,141 M84,150 L116,150', DARK, 3), L('M92,128 L94,100 L106,100 L108,128', PEACH, 3),
                          L('M30,64 L44,70 M170,64 L156,70 M100,10 L100,22 M46,26 L56,38 M154,26 L144,38', WHITE, 5)],
 'kendrick-lamar': lambda: [F(poly([(38,146),(32,62),(70,100),(100,52),(130,100),(168,62),(162,146)]), BUTTER), F(rect(36, 136, 128, 22, 4), PEACH),
                            F(circle(100, 100, 9), PINK), F(circle(32, 60, 7), WHITE), F(circle(100, 50, 7), WHITE), F(circle(168, 60, 7), WHITE)],
 'lana-del-rey': lambda: [L('M74,114 C80,80 100,56 116,40 M128,106 C126,80 120,60 116,40', GREEN, 6), F('M116,40 C130,24 156,26 164,34 C148,46 130,48 116,40Z', MINT),
                          F(circle(72, 136, 24), RED), F(circle(130, 128, 24), RED), L('M60,128 C62,122 66,118 70,118', WHITE, 4)],
 'laufey': lambda: [F('M100,54 C76,54 70,72 75,86 C78,94 70,98 66,110 C58,136 72,166 100,166 C128,166 142,136 134,110 C130,98 122,94 125,86 C130,72 124,54 100,54Z', PEACH),
                    L('M100,58 L100,14', TAN, 9), L('M96,40 L96,150 M104,40 L104,150', WHITE, 2), L('M82,112 C78,120 84,126 80,134 M118,112 C122,120 116,126 120,134', DARK, 3),
                    F(rect(90, 140, 20, 8, 2), DARK), L('M100,166 L100,184', DARK, 4)],
 'lizzy-mcalpine': lambda: [L('M100,58 L100,40 M86,38 L114,38 M146,70 L156,60', WHITE, 7), F(circle(100, 112, 54), BLUE), F(circle(100, 112, 40), WHITE, light=True),
                            L('M100,112 L100,82 M100,112 L120,124', DARK, 6)],
 'lorde': lambda: [L('M100,170 L100,186', WHITE, 8), F(rect(66, 26, 68, 146, 16), PERI), F(circle(100, 56, 16), DARK), F(circle(100, 99, 16), DARK), F(circle(100, 142, 18), GREEN)],
 'lucy-dacus': lambda: [L('M100,64 L74,30 M100,64 L130,26', WHITE, 5), F(rect(36, 62, 128, 96, 14), PINK), F(rect(50, 76, 82, 68, 10), BLUE),
                        F(circle(148, 92, 6), DARK), F(circle(148, 114, 6), DARK), L('M60,90 L72,82', WHITE, 4)],
 'mitski': lambda: [F(rect(48, 34, 104, 138, 12), WHITE), F(circle(100, 112, 36), BLUE), L(circle(100, 112, 44), PERI, 5), F(heart(100, 114, 18), RED),
                    L('M56,56 L144,56', PERI, 3), F(circle(66, 45, 4), DARK), F(circle(82, 45, 4), DARK), F(rect(110, 42, 32, 7, 3), LILAC)],
 'noah-kahan': leaf,
 'olivia-rodrigo': lambda: [L(ellipse(78, 104, 27, 40, 14), PINK, 7), L(ellipse(73, 104, 24, 38, 14), PINK, 4),  # her OR monogram
                            L('M66,152 C92,140 110,112 118,80', PINK, 5), L('M82,86 C102,96 132,92 144,72 C154,54 146,38 130,40 C116,42 110,60 122,64 C132,66 134,54 126,52', PINK, 6),
                            L('M104,96 C118,98 112,112 116,128 C120,146 138,152 146,142 C152,134 144,126 140,134', PINK, 6)],
 'paramore': lambda: [F('M22,100 C60,46 140,46 178,100 C140,154 60,154 22,100Z', WHITE), F(circle(100, 100, 28), SKY), F(circle(100, 100, 11), DARK),
                      L('M58,60 L48,44 M86,50 L82,32 M114,50 L118,32 M142,60 L152,44', WHITE, 5)],
 'phoebe-bridgers': lambda: [F('M58,170 L58,92 C58,44 142,44 142,92 L142,170 L128,156 L114,170 L100,156 L86,170 L72,156Z', WHITE),
                             F(ellipse(84, 96, 9, 12), DARK), F(ellipse(116, 96, 9, 12), DARK)],
 'post-malone': sunflower,
 'renee-rapp': snowflake,
 'role-model': lambda: [F('M66,66 L134,66 C134,92 122,106 100,108 C78,106 66,92 66,66Z', RED), L('M64,36 L136,36 C139,84 126,106 100,110 C74,106 61,84 64,36Z', WHITE, 5),
                        L('M100,110 L100,162 M72,166 L128,166', WHITE, 7)],
 'sabrina-carpenter': lambda: [F('M26,100 C48,76 70,68 86,74 C93,77 96,82 100,82 C104,82 107,77 114,74 C130,68 152,76 174,100 C140,104 120,98 100,104 C80,98 60,104 26,100Z', HOT),
                               F('M26,102 C60,106 80,102 100,106 C120,102 140,106 174,102 C152,138 126,148 100,148 C74,148 48,138 26,102Z', PINK), L('M80,124 C86,130 96,132 104,130', WHITE, 4)],
 'sombr': lambda: [L('M100,108 C98,134 104,156 98,180', GREEN, 7), F('M100,128 C80,112 62,120 58,134 C78,138 90,136 100,128Z', MINT),
                   F('M54,52 C54,96 74,114 100,114 C126,114 146,96 146,52 C132,64 118,60 110,46 C104,58 96,58 90,46 C82,60 68,64 54,52Z', RED),
                   L('M74,60 C78,40 122,36 126,58 C128,74 106,82 96,72 C90,64 98,56 106,60', RED, 6), L('M70,86 C84,98 116,98 130,86', RED, 4)],
 'sza': lambda: [F(circle(100, 100, 66) + circle(100, 100, 34), WHITE, evenodd=True)] + [F(sector(100, 100, 34, 66, a, a + 40), RED) for a in (20, 110, 200, 290)] + [L(circle(100, 100, 50), PERI, 3)],
 'tame-impala': spiral,
 'taylor-swift': lambda: [L('M54,62 L76,44 L76,156 M56,156 L96,156', PINK, 11), L('M112,58 C126,40 162,42 162,72 C162,94 138,98 126,98 C142,98 166,106 166,130 C166,162 126,168 108,148', LILAC, 11)],
 'the-1975': lambda: [L(rect(34, 58, 132, 84, 2), PINK, 9), L(rect(34, 58, 132, 84, 2), WHITE, 3)],
 'the-marias': lambda: [L('M112,62 L112,34 L132,34', WHITE, 6), F(rect(88, 58, 44, 34, 8), RED), F('M22,118 C22,90 60,86 100,86 C140,86 172,96 176,118 C172,140 140,150 100,150 C60,150 22,146 22,118Z', RED),
                        F(circle(76, 118, 11), BLUE), F(circle(108, 118, 11), BLUE), F(circle(140, 118, 11), BLUE), F(poly([(176,118),(190,104),(190,132)]), PINK),
                        L(circle(40, 68, 6) + circle(52, 46, 4), WHITE, 3)],
 'the-strokes': guitar,
 'the-weeknd': lambda: [L('M32,58 L88,146 M88,58 L32,146', RED, 12), L(ellipse(140, 102, 30, 44), RED, 12)],
 'tyler-the-creator': bee,
 'vampire-weekend': globe,
 'wallows': lambda: [F(rect(26, 58, 148, 94, 10), MINT), F(rect(42, 70, 116, 40, 5), PINK), F(circle(76, 92, 13), DARK), F(circle(124, 92, 13), DARK),
                     L(circle(76, 92, 5) + circle(124, 92, 5), WHITE, 3), F(poly([(60,152),(70,128),(130,128),(140,152)]), BLUE)],
}

# ---- crayon renderer ----
# Every mark is drawn in one dark wax crayon on a pastel circle; the circle takes the
# symbol's own colour. Filled shapes are outlined and loosely shaded, as a person would.
INK = '#1e1c2e'

def scribble(rng, angle, gap, jitter=1.6):
  pts, y, flip = [], -140.0, False
  while y < 140:
    xs = [-140 + i*40 for i in range(8)]
    if flip: xs.reverse()
    for x in xs: pts.append((x + rng.uniform(-3, 3), y + rng.uniform(-jitter, jitter)))
    y += gap*rng.uniform(.75, 1.25); flip = not flip
  d = 'M' + 'L'.join(f'{x:.1f},{yy:.1f}' for x, yy in pts)
  return f'<path d="{d}" transform="translate(100 100) rotate({angle:.0f})"/>'

def background(parts):
  counts = {}
  for kind, d, color, k in parts:
    if color not in (DARK, WHITE): counts[color] = counts.get(color, 0) + (3 if kind == 'fill' else 1)
  return max(counts, key=counts.get) if counts else LILAC

OFFSETS = OUT.parent.parent / 'scripts' / 'mark-offsets.json'  # measured by the browser so every symbol sits in the middle

def render(slug, parts, offset=(0, 0)):
  bg = background(parts)
  rng = random.Random(int(hashlib.md5(slug.encode()).hexdigest()[:8], 16))
  defs, body = [], []
  for i, (kind, d, color, k) in enumerate(parts):
    cid = f'c{i}'
    rule = ' clip-rule="evenodd"' if k.get('evenodd') else ''
    fillrule = ' fill-rule="evenodd"' if k.get('evenodd') else ''
    defs.append(f'<clipPath id="{cid}"><path d="{d}"{rule}/></clipPath>')
    wrap = f' transform="{k["tf"]}"' if k.get('tf') else ''
    if k.get('clip'):
      defs.append(f'<clipPath id="{cid}x"><path d="{k["clip"]}"/></clipPath>'); wrap = f' clip-path="url(#{cid}x)"' + wrap
    if kind == 'fill':
      solid = color == DARK
      a = rng.uniform(-50, 50); gap = 5 if solid else rng.uniform(10, 13); op = .95 if solid else .42
      if k.get('opaque'): body.append(f'<path d="{d}" fill="{bg}"{wrap}/>')
      body.append(f'<g{wrap}><g clip-path="url(#{cid})" fill="none" stroke="{INK}" stroke-linecap="round" stroke-linejoin="round" opacity="{op}">'
                  f'<g stroke-width="{6 if solid else 3.2}">{scribble(rng, a, gap)}</g></g>'
                  f'<path d="{d}"{fillrule} fill="none" stroke="{INK}" stroke-width="6.5" stroke-linejoin="round" stroke-linecap="round"/>'
                  f'<path d="{d}"{fillrule} fill="none" stroke="{INK}" stroke-width="3.5" opacity=".6" transform="translate({rng.uniform(1,2.2):.1f} {rng.uniform(-1.5,1.5):.1f})"/></g>')
    else:
      w = k['w'] if color == DARK or k.get('thin') else max(7, min(k['w'], 11))
      if k.get('knock'):
        body.append(f'<path d="{d}"{wrap} fill="none" stroke="{bg}" stroke-width="{w}" stroke-linecap="butt" stroke-linejoin="round"/>'); continue
      body.append(f'<g{wrap} fill="none" stroke="{INK}" stroke-linecap="round" stroke-linejoin="round">'
                  f'<path d="{d}" stroke-width="{w}"/><path d="{d}" stroke-width="{max(2, w*.5):.1f}" opacity=".6" transform="translate({rng.uniform(1,2.2):.1f} {rng.uniform(-1.5,1.5):.1f})"/></g>')
  s1, s2, s3 = rng.randint(1, 999), rng.randint(1, 999), rng.randint(1, 999)
  flt = ('<filter id="crayon" x="0" y="0" width="200" height="200" filterUnits="userSpaceOnUse">'
         f'<feTurbulence type="fractalNoise" baseFrequency="0.03" numOctaves="2" seed="{s1}" result="w"/>'
         '<feDisplacementMap in="SourceGraphic" in2="w" scale="5" xChannelSelector="R" yChannelSelector="G" result="d1"/>'
         f'<feTurbulence type="fractalNoise" baseFrequency="0.7" numOctaves="2" seed="{s2}" result="f"/>'
         '<feDisplacementMap in="d1" in2="f" scale="3.2" xChannelSelector="R" yChannelSelector="G" result="d2"/>'
         f'<feTurbulence type="fractalNoise" baseFrequency="1.1" numOctaves="3" seed="{s3}" result="g"/>'
         '<feColorMatrix in="g" type="matrix" values="0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 -3.4 2.75" result="m"/>'
         '<feComposite in="d2" in2="m" operator="in" result="t"/><feGaussianBlur in="t" stdDeviation="0.5"/></filter>'
         '<filter id="paper" x="0" y="0" width="200" height="200" filterUnits="userSpaceOnUse">'
         f'<feTurbulence type="fractalNoise" baseFrequency="0.8" numOctaves="2" seed="{s1}" result="n"/>'
         '<feColorMatrix in="n" type="matrix" values="0 0 0 0 1 0 0 0 0 1 0 0 0 0 1 0 0 0 .5 -.18" result="speck"/>'
         '<feComposite in="speck" in2="SourceGraphic" operator="in" result="s"/><feMerge><feMergeNode in="SourceGraphic"/><feMergeNode in="s"/></feMerge></filter>')
  return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200" width="200" height="200">'
          f'<defs>{flt}{"".join(defs)}</defs><circle cx="100" cy="100" r="100" fill="{bg}" filter="url(#paper)"/>'
          f'<g transform="translate(100 100) scale(.84) translate(-100 -100)"><g filter="url(#crayon)" transform="translate({offset[0]:.1f} {offset[1]:.1f})">{"".join(body)}</g></g></svg>\n')

if __name__ == '__main__':
  OUT.mkdir(parents=True, exist_ok=True)
  import json
  offsets = json.loads(OFFSETS.read_text()) if OFFSETS.exists() else {}
  for slug, make in SYMBOLS.items():
    (OUT / f'{slug}.svg').write_text(render(slug, make(), offsets.get(slug, (0, 0))), encoding='utf-8')
  print(len(SYMBOLS), 'marks written to', OUT)
