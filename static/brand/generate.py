"""Generateur des fichiers de marque Competences+.

    uv run --no-project --with fonttools --with brotli --with uharfbuzz \
        python static/brand/generate.py

Puis, pour les declinaisons matricielles (rsvg-convert, paquet librsvg) :

    rsvg-convert -w 32   -h 32   static/brand/favicon-source.svg    -o static/favicon-32.png
    rsvg-convert -w 180  -h 180  static/brand/apple-touch-source.svg -o static/apple-touch-icon.png
    rsvg-convert -w 1200 -h 630  static/brand/og.svg                 -o static/og-competences-plus.png


Le mot-symbole est compose dans la Poppins deja auto-hebergee par le site,
puis converti en courbes : le SVG ne depend donc d'aucune police installee.
Le signe « + » n'est pas le glyphe de la police mais une croix geometrique
dessinee ici, aux terminaisons arrondies et au gras legerement superieur aux
fûts des lettres, pour qu'il se lise comme un accent et non comme une lettre.
"""

import math
import os
import tempfile

import uharfbuzz as hb
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BRAND = f"{ROOT}/static/brand"
FONT = f"{ROOT}/static/fonts/Poppins-SemiBold.woff2"

WORD = "Compétences"
TRACKING = -14          # resserrement du mot, en 1/1000 d'em
GAP = 90                # blanc optique entre le « s » et le « + »

BLEU = "#1b3a6b"        # --color-primary
ORANGE = "#d9631a"      # --color-secondary


# --------------------------------------------------------------------------
# Polygone a coins arrondis. Gere les sommets convexes et concaves (les
# aisselles de la croix) en choisissant le sens de l'arc d'apres le produit
# vectoriel des deux aretes.
# --------------------------------------------------------------------------
def rounded_polygon(points, radius):
    n = len(points)
    out = []
    for i in range(n):
        prev = points[(i - 1) % n]
        cur = points[i]
        nxt = points[(i + 1) % n]

        v1 = (prev[0] - cur[0], prev[1] - cur[1])
        v2 = (nxt[0] - cur[0], nxt[1] - cur[1])
        l1 = math.hypot(*v1)
        l2 = math.hypot(*v2)
        u1 = (v1[0] / l1, v1[1] / l1)
        u2 = (v2[0] / l2, v2[1] / l2)

        r = min(radius, l1 / 2, l2 / 2)
        p1 = (cur[0] + u1[0] * r, cur[1] + u1[1] * r)
        p2 = (cur[0] + u2[0] * r, cur[1] + u2[1] * r)

        cross = v1[0] * v2[1] - v1[1] * v2[0]
        sweep = 0 if cross > 0 else 1
        out.append((p1, p2, r, sweep))

    d = f"M{out[0][0][0]:.1f},{out[0][0][1]:.1f}"
    for p1, p2, r, sweep in out:
        d += f"L{p1[0]:.1f},{p1[1]:.1f}"
        d += f"A{r:.1f},{r:.1f} 0 0 {sweep} {p2[0]:.1f},{p2[1]:.1f}"
    return d + "Z"


def plus_path(cx, cy, size, thickness, radius, inner_radius=None):
    """Croix a 12 sommets, centree sur (cx, cy). Un seul contour ferme :
    utilisable telle quelle comme decoupe (fill-rule evenodd)."""
    h = size / 2
    a = thickness / 2
    pts = [
        (cx - a, cy - h), (cx + a, cy - h),
        (cx + a, cy - a), (cx + h, cy - a),
        (cx + h, cy + a), (cx + a, cy + a),
        (cx + a, cy + h), (cx - a, cy + h),
        (cx - a, cy + a), (cx - h, cy + a),
        (cx - h, cy - a), (cx - a, cy - a),
    ]
    # Les aisselles recoivent un rayon plus doux que les terminaisons.
    ir = inner_radius if inner_radius is not None else radius * 0.55
    n = len(pts)
    out = []
    for i in range(n):
        prev, cur, nxt = pts[(i - 1) % n], pts[i], pts[(i + 1) % n]
        v1 = (prev[0] - cur[0], prev[1] - cur[1])
        v2 = (nxt[0] - cur[0], nxt[1] - cur[1])
        cross = v1[0] * v2[1] - v1[1] * v2[0]
        concave = cross > 0
        r = ir if concave else radius
        l1, l2 = math.hypot(*v1), math.hypot(*v2)
        r = min(r, l1 / 2, l2 / 2)
        u1 = (v1[0] / l1, v1[1] / l1)
        u2 = (v2[0] / l2, v2[1] / l2)
        p1 = (cur[0] + u1[0] * r, cur[1] + u1[1] * r)
        p2 = (cur[0] + u2[0] * r, cur[1] + u2[1] * r)
        out.append((p1, p2, r, 0 if concave else 1))

    d = f"M{out[0][0][0]:.1f},{out[0][0][1]:.1f}"
    for p1, p2, r, sweep in out:
        d += f"L{p1[0]:.1f},{p1[1]:.1f}"
        d += f"A{r:.1f},{r:.1f} 0 0 {sweep} {p2[0]:.1f},{p2[1]:.1f}"
    return d + "Z"


def rounded_rect(x, y, w, h, r):
    return rounded_polygon([(x, y), (x + w, y), (x + w, y + h), (x, y + h)], r)


# --------------------------------------------------------------------------
# Composition d'une chaine en courbes (Poppins, via HarfBuzz pour le crenage).
# --------------------------------------------------------------------------
_ttf_cache = {}


def as_ttf(woff2_path):
    if woff2_path not in _ttf_cache:
        f = TTFont(woff2_path)
        tmp = tempfile.NamedTemporaryFile(suffix=".ttf", delete=False)
        tmp.close()
        f.flavor = None
        f.save(tmp.name)
        _ttf_cache[woff2_path] = tmp.name
    return _ttf_cache[woff2_path]


def outline(text, woff2_path, tracking=0):
    """Rend `text` en un seul chemin SVG, repere y-vers-le-bas, origine sur la
    ligne de base. Retourne (chemin, bornes, chasse totale)."""
    font = TTFont(woff2_path)
    glyphset = font.getGlyphSet()

    blob = hb.Blob.from_file_path(as_ttf(woff2_path))
    hbfont = hb.Font(hb.Face(blob))
    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    hb.shape(hbfont, buf, {"kern": True, "liga": True})

    paths = []
    pen_x = 0.0
    bounds = [1e9, 1e9, -1e9, -1e9]
    for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
        name = font.getGlyphName(info.codepoint)
        transform = (1, 0, 0, -1, pen_x + pos.x_offset, 0)

        spen = SVGPathPen(glyphset)
        glyphset[name].draw(TransformPen(spen, transform))
        d = spen.getCommands()
        if d:
            paths.append(d)

        bpen = BoundsPen(glyphset)
        glyphset[name].draw(TransformPen(bpen, transform))
        if bpen.bounds:
            x0, y0, x1, y1 = bpen.bounds
            bounds = [min(bounds[0], x0), min(bounds[1], y0),
                      max(bounds[2], x1), max(bounds[3], y1)]

        pen_x += pos.x_advance + tracking

    return " ".join(paths), bounds, pen_x


font = TTFont(FONT)
upem = font["head"].unitsPerEm
cap = font["OS/2"].sCapHeight

word_d, bounds, _ = outline(WORD, FONT, TRACKING)
word_right = bounds[2]

# --------------------------------------------------------------------------
# Le « + » : hauteur de capitale, aligne sur la hauteur des majuscules,
# fûts un peu plus gras que ceux des lettres.
# --------------------------------------------------------------------------
PLUS_SIZE = cap * 0.86
PLUS_THICK = cap * 0.225
PLUS_R = PLUS_THICK * 0.5

plus_cx = word_right + GAP + PLUS_SIZE / 2
plus_cy = -cap / 2                      # repere deja inverse : cap est vers -y
plus_d = plus_path(plus_cx, plus_cy, PLUS_SIZE, PLUS_THICK, PLUS_R)

# --------------------------------------------------------------------------
# Cadrage
# --------------------------------------------------------------------------
PAD = 40
min_x = min(bounds[0], plus_cx - PLUS_SIZE / 2) - PAD
max_x = max(word_right, plus_cx + PLUS_SIZE / 2) + PAD
min_y = min(bounds[1], plus_cy - PLUS_SIZE / 2) - PAD
max_y = max(bounds[3], plus_cy + PLUS_SIZE / 2) + PAD
vb_w = max_x - min_x
vb_h = max_y - min_y


def svg(body, w, h, vb, extra=""):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}" '
        f'width="{w:.0f}" height="{h:.0f}" role="img"{extra}>\n{body}\n</svg>\n'
    )


VB = f"{min_x:.1f} {min_y:.1f} {vb_w:.1f} {vb_h:.1f}"
DISP_H = 96
DISP_W = DISP_H * vb_w / vb_h

title = '<title>Compétences+</title>'

# 1. Logotype couleur
open(f"{BRAND}/logotype.svg", "w", encoding="utf-8").write(svg(
    f'  {title}\n'
    f'  <path fill="{BLEU}" d="{word_d}"/>\n'
    f'  <path fill="{ORANGE}" d="{plus_d}"/>',
    DISP_W, DISP_H, VB))

# 2. Logotype monochrome : une seule encre, pilotable par currentColor.
open(f"{BRAND}/logotype-mono.svg", "w", encoding="utf-8").write(svg(
    f'  {title}\n'
    f'  <g fill="currentColor">\n'
    f'    <path d="{word_d}"/>\n'
    f'    <path d="{plus_d}"/>\n'
    f'  </g>',
    DISP_W, DISP_H, VB, extra=f' color="{BLEU}"'))

# --------------------------------------------------------------------------
# Le symbole seul : la croix evidee dans une tuile arrondie. Comme le « + »
# est un trou et non une forme blanche, la tuile reste lisible sur n'importe
# quel fond et supporte l'aplat monochrome de la barre de navigation.
# --------------------------------------------------------------------------
def mark(size, tile_r_ratio, plus_ratio, thick_ratio, color, mono=False):
    tile = rounded_rect(0, 0, size, size, size * tile_r_ratio)
    p = plus_path(size / 2, size / 2, size * plus_ratio,
                  size * thick_ratio, size * thick_ratio * 0.5)
    fill = 'currentColor' if mono else color
    extra = f' color="{color}"' if mono else ""
    body = (f'  <title>Compétences+</title>\n'
            f'  <path fill="{fill}" fill-rule="evenodd" d="{tile} {p}"/>')
    return svg(body, size, size, f"0 0 {size:.0f} {size:.0f}", extra), extra


S = 256
open(f"{BRAND}/mark.svg", "w", encoding="utf-8").write(
    mark(S, 0.235, 0.50, 0.135, ORANGE)[0])
open(f"{BRAND}/mark-mono.svg", "w", encoding="utf-8").write(
    mark(S, 0.235, 0.50, 0.135, BLEU, mono=True)[0])
# Favicon : croix plus grasse et coins moins ronds, pour tenir a 16 px.
open(f"{ROOT}/static/favicon.svg", "w", encoding="utf-8").write(
    mark(S, 0.21, 0.56, 0.165, ORANGE)[0])



# --------------------------------------------------------------------------
# Declinaisons matricielles.
#
# Le « + » evide convient au SVG, mais un PNG de favicon peut atterrir sur un
# fond sombre : on y grave donc une croix blanche pleine plutot qu'un trou.
# L'icone iOS est a fond perdu, sans coins arrondis : le systeme applique son
# propre masque.
# --------------------------------------------------------------------------
def mark_solid(size, tile_r_ratio, plus_ratio, thick_ratio, tile, ink):
    body = (f'  <title>Compétences+</title>\n'
            f'  <path fill="{tile}" d="{rounded_rect(0, 0, size, size, size * tile_r_ratio)}"/>\n'
            f'  <path fill="{ink}" d="{plus_path(size / 2, size / 2, size * plus_ratio, size * thick_ratio, size * thick_ratio * 0.5)}"/>')
    return svg(body, size, size, f"0 0 {size:.0f} {size:.0f}")


open(f"{BRAND}/favicon-source.svg", "w", encoding="utf-8").write(
    mark_solid(256, 0.21, 0.56, 0.165, ORANGE, "#ffffff"))
open(f"{BRAND}/apple-touch-source.svg", "w", encoding="utf-8").write(
    mark_solid(256, 0.0, 0.52, 0.155, ORANGE, "#ffffff"))

# --------------------------------------------------------------------------
# Carte de partage (og:image), 1200x630. Fond bleu de marque, mot-symbole en
# blanc, « + » dans le jaune d'action : le contraste passe dans les fils
# d'actualite comme dans les apercus de messagerie.
# --------------------------------------------------------------------------
JAUNE = "#f6d179"
OG_W, OG_H = 1200, 630
MARGIN = 96
TAGLINE = "Les bonnes données pour le bon recrutement."

lock_x0 = bounds[0]
lock_x1 = plus_cx + PLUS_SIZE / 2
lock_w = lock_x1 - lock_x0

k = 840 / lock_w
baseline = 330
tx = MARGIN - k * lock_x0

tag_d, tag_bounds, _ = outline(TAGLINE, f"{ROOT}/static/fonts/Poppins-Medium.woff2")
kt = 34 / 1000
tag_tx = MARGIN - kt * tag_bounds[0]
tag_baseline = 448

rule_y = 502
og = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {OG_W} {OG_H}" width="{OG_W}" height="{OG_H}">
  <title>Compétences+</title>
  <rect width="{OG_W}" height="{OG_H}" fill="{BLEU}"/>
  <g transform="translate({tx:.1f},{baseline}) scale({k:.5f})">
    <path fill="#ffffff" d="{word_d}"/>
    <path fill="{JAUNE}" d="{plus_d}"/>
  </g>
  <g transform="translate({tag_tx:.1f},{tag_baseline}) scale({kt:.5f})">
    <path fill="#ffffff" fill-opacity="0.72" d="{tag_d}"/>
  </g>
  <rect x="{MARGIN}" y="{rule_y}" width="72" height="6" rx="3" fill="{JAUNE}"/>
</svg>
'''
open(f"{BRAND}/og.svg", "w", encoding="utf-8").write(og)
print("SVG ecrits dans static/brand/ ; favicon.svg dans static/")
