import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "output" / "build"
PANELS = ROOT / "output" / "panels" / "test"
BUILD.mkdir(parents=True, exist_ok=True)
PANELS.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import base64
import html
import json

S = BUILD
A = S / "img"
OUT = S / "board.html"

SHEET0, SHEET1 = 29.632, 86.300
SPAN = SHEET1 - SHEET0


def img_uri(name):
    return "data:image/jpeg;base64," + base64.b64encode((A / (name + ".jpg")).read_bytes()).decode()


IMG = {p.stem: img_uri(p.stem) for p in A.glob("*.jpg")}
VIDEO = "data:video/mp4;base64," + base64.b64encode((S / "prev_web.mp4").read_bytes()).decode()

ENTITIES = [
    dict(tag="man", kind="Character", plate="A_man", seed="20260826", cr="5 cr",
         desc="Man, thirties, weathered sunburnt face, short black hair, "
              "faded blue collared work shirt"),
    dict(tag="desert", kind="Location", plate="B_desert", seed="20260826", cr="5 cr",
         desc="Sonoran Desert, sun-bleached cracked earth, distant rocky "
              "mountains, dry wash, towering saguaros"),
    dict(tag="desert_tall", kind="Plate 1080\u00d71920", plate="F_tall", seed="31415",
         cr="8 cr",
         desc="The same location built tall, horizon to ground in one unbroken "
              "view, so a 16:9 window can crane down it"),
]

# start, end, dur are the measured extents. `panels` is a list -- one shot may be
# sampled at several moments, which is what V1-A carrying over means.
CELLS = [
    dict(slate="V1-A", section="Verse 1", size="wide tracking shot", lens="wide angle",
         start=29.632, end=43.573, dur=13.941, movement="tracking, following",
         direction="left to right", method="generate", state="approved",
         ents=["man", "desert"], expanded=True, wide=True,
         panels=[dict(img="C_composed", at=29.632, sub="A/1"),
                 dict(img="G_follow", at=36.715, sub="A/2")],
         action="Camera travels with him, staying behind his shoulder. Two beats of the "
                "same unbroken walk.",
         lyric="I'm walking through the Aero Desert / Hot day pressed on my back / "
               "Boot soles full of grit",
         info="One shot, two panels \u2014 the 180_degree structure. Sampled at 29.632 s "
              "and 36.715 s, which is one aleph2 call with two keyframes.",
         prompt="Tracking shot following @man from behind as he walks through @desert, "
                "camera moving with him at his pace, dust kicked up around his boots, "
                "mountains closer, cinematic realism, poetic documentary photography, "
                "dramatic natural light, restrained earth tones, subtle film grain"),
    dict(slate="V1-B", section="Verse 1", size="extreme wide shot", lens="wide angle",
         start=43.573, end=50.379, dur=6.806, movement="static locked-off",
         direction="left to right", method="generate", state="undrawn",
         ents=["man", "desert"], expanded=False,
         panels=[dict(img=None, at=43.573, sub="B")],
         action="Locked off. He enters frame left, crosses, exits frame right. Nothing "
                "else moves.",
         lyric="My throat gone thin and black / Blisters raging, red and raw",
         prompt="@man crosses @desert left to right in an extreme wide static shot, "
                "full sun overhead, cracked earth, cinematic realism, subtle film grain"),
    dict(slate="V1-C", section="Verse 1", size="wide shot", lens="wide angle",
         start=50.379, end=59.211, dur=8.832, movement="very slow push in",
         direction="toward camera", method="generate", state="redraw",
         ents=["man"], expanded=False,
         panels=[dict(img="A_man", at=50.379, sub="C")],
         flag="Panel is a close-up; the row calls for a wide shot. Redraw before approving.",
         action="Push in as he comes toward camera. Face still unreadable at this size.",
         lyric="Every step pulls skin / Sun keeps staring down / Like it wants to win",
         prompt="Very slow push in on @man walking toward camera across cracked desert "
                "ground, wide shot, full figure, harsh overhead sun, cinematic realism, "
                "subtle film grain"),
    dict(slate="PC-A", section="Pre-Chorus", size="extreme wide shot", lens="wide angle",
         start=59.211, end=66.261, dur=7.050, movement="static locked-off",
         direction="left to right", method="generate", state="unmatched",
         ents=["man"], expanded=False,
         panels=[dict(img="D_face", at=59.211, sub="A")],
         flag="Anchor \u201cI\u2019m losing shape out here\u201d matched no line in the "
              "aligned lyric timeline, so this row has no measured position and the "
              "planner discards it. It is the 7.05 s hole on the timeline.",
         action="He is fading in the heat haze. Barely holding shape.",
         lyric="I'm losing shape out here / My shadow's barely mine",
         prompt="Low angle close-up of @man on his knees on cracked desert ground, head "
                "tilted back, mouth open shouting upward, harsh overhead noon sun, "
                "cinematic realism"),
    dict(slate="C-A", section="Chorus", size="crane down", lens="wide angle",
         start=66.261, end=86.300, dur=20.039, movement="crane down, ease in out",
         direction="downward", method="composite", state="approved",
         ents=["desert_tall"], expanded=False, crane=True,
         panels=[dict(img="F_tall", at=66.261, sub="A")],
         action="One continuous crane from the mountains down to the cracked ground. "
                "No cuts. Twenty seconds.",
         lyric="Face in the dust / Face in the dust / I fell so hard",
         info="20.039 s cannot be bought as video \u2014 Runway caps a clip at 10 s. This "
              "is a crop path over the tall plate, run in ffmpeg. Frame-exact, 0 cr.",
         prompt="[composite] plate @desert_tall at 1080:1920. Crop 1080\u00d7608 window, "
                "y travels 0 \u2192 1312, ease in out over 20.039 s. No generation."),
]

STATE_LABEL = {"approved": "Approved", "undrawn": "Not drawn",
               "redraw": "Redraw", "unmatched": "Unmatched anchor"}

# ---------------------------------------------------------------- timeline data
# PC-A is unmatched, so it has no position -- the hole is what its absence looks like.
TL = []
for c in CELLS:
    if c["state"] == "unmatched":
        TL.append(dict(kind="hole", slate="HOLE", label="no row",
                       t0=c["start"] - SHEET0, t1=c["end"] - SHEET0, dur=c["dur"]))
    else:
        TL.append(dict(kind="shot", slate=c["slate"], label=c["slate"],
                       t0=c["start"] - SHEET0, t1=c["end"] - SHEET0, dur=c["dur"],
                       img=c["panels"][0]["img"], method=c["method"],
                       state=c["state"], size=c["size"],
                       n=len(c["panels"]),
                       panels=[p["at"] - SHEET0 for p in c["panels"]]))


def pct(v):
    return "%.4f%%" % (v / SPAN * 100)


BLOCKS = []
for b in TL:
    style = "left:%s;width:%s" % (pct(b["t0"]), pct(b["dur"]))
    if b["kind"] == "hole":
        BLOCKS.append(
            '<div class="blk blk-hole" data-slate="HOLE" data-t0="%.3f" style="%s">'
            '<div class="blk-l"><b>no row</b><i>%.2f s falls to the arc</i></div>'
            '</div>' % (b["t0"], style, b["dur"]))
        continue
    cls = "blk" + (" blk-undrawn" if b["state"] == "undrawn" else "")
    bg = ("background-image:url(%s);" % IMG[b["img"]]) if b["img"] else ""
    npanel = ('<span class="npanel">%d panels</span>' % b["n"]) if b["n"] > 1 else ""
    mdot = ('<span class="mthdot">composite</span>' if b["method"] == "composite" else "")
    BLOCKS.append(
        '<div class="%s" data-slate="%s" data-t0="%.3f" style="%s%s">%s%s'
        '<div class="blk-l"><b>%s</b><i>%.3f s &middot; %s</i></div></div>'
        % (cls, b["slate"], b["t0"], bg, style, npanel, mdot,
           b["slate"], b["dur"], html.escape(b["size"])))

SECS = []
for label, t0, t1 in (("Verse 1", 29.632, 59.211), ("Pre-Chorus", 59.211, 66.261),
                      ("Chorus", 66.261, 86.300)):
    SECS.append('<i style="left:%s;width:%s">%s</i>'
                % (pct(t0 - SHEET0), pct(t1 - t0), label))

ANALYSIS = ROOT / "output" / "analysis" / "Face in the dust.json"
analysis = json.loads(ANALYSIS.read_text(encoding="utf-8"))
dbs = [t for t in analysis["downbeats"] if SHEET0 <= t <= SHEET1]
TICKS = "".join('<i class="%s" style="left:%s"></i>'
                % ("bar4" if i % 4 == 0 else "", pct(t - SHEET0))
                for i, t in enumerate(dbs))

SHOTS_JS = json.dumps([
    dict(slate=b["slate"], label=("&mdash; no row" if b["kind"] == "hole" else b["label"]),
         t0=round(b["t0"], 3), t1=round(b["t1"], 3),
         panels=[round(x, 3) for x in b.get("panels", [])])
    for b in TL])


# ------------------------------------------------------------------ board cells
def overlay(c):
    if c.get("crane"):
        # tall plate shown contained in a 16:9 box: image spans x 109.5..210.5
        return ('<svg class="ovl" viewBox="0 0 320 180" aria-hidden="true">'
                '<rect class="crop" x="110" y="1" width="100" height="56"></rect>'
                '<text class="croplab" x="114" y="14">A</text>'
                '<rect class="crop" x="110" y="123" width="100" height="56"></rect>'
                '<text class="croplab" x="114" y="136">B</text>'
                '<path class="arw" d="M160 62 L160 118" marker-end="url(#ah)"></path>'
                '</svg>')
    m, d = c["movement"], c["direction"]
    if "push in" in m:
        return ('<svg class="ovl" viewBox="0 0 320 180" aria-hidden="true">'
                '<rect class="crop" x="86" y="46" width="148" height="88"></rect>'
                '<path class="arw" d="M34 20 L80 42" marker-end="url(#ah)"></path>'
                '<path class="arw" d="M286 20 L240 42" marker-end="url(#ah)"></path>'
                '<path class="arw" d="M34 160 L80 138" marker-end="url(#ah)"></path>'
                '<path class="arw" d="M286 160 L240 138" marker-end="url(#ah)"></path></svg>')
    if "tracking" in m or "following" in m:
        # subject holds frame, ground travels -- two arrows say "the camera moves too"
        return ('<svg class="ovl" viewBox="0 0 320 180" aria-hidden="true">'
                '<path class="arw" d="M112 164 L208 164" marker-end="url(#ah)"></path>'
                '<path class="arw" d="M64 150 L28 150" marker-end="url(#ah)"></path>'
                '<path class="arw" d="M256 150 L292 150" marker-end="url(#ah)"></path></svg>')
    if d == "left to right":
        return ('<svg class="ovl" viewBox="0 0 320 180" aria-hidden="true">'
                '<path class="arw" d="M96 148 L224 148" marker-end="url(#ah)"></path></svg>')
    return ('<svg class="ovl" viewBox="0 0 320 180" aria-hidden="true">'
            '<circle class="crop" cx="160" cy="90" r="30"></circle>'
            '<path class="arw" d="M160 150 L160 126" marker-end="url(#ah)"></path></svg>')


def ent_chips(c):
    out = []
    for e in ENTITIES:
        on = e["tag"] in c["ents"]
        out.append('<button type="button" class="chip ent%s" data-tag="%s" '
                   'aria-pressed="%s">@%s</button>'
                   % (" on" if on else "", e["tag"], "true" if on else "false", e["tag"]))
    return "".join(out)


def tc(t):
    return "%d:%05.2f" % (int(t // 60), t % 60)


def cell_html(c, i):
    plates = []
    for p in c["panels"]:
        if p["img"]:
            style = ' style="object-fit:contain;background:var(--sunk)"' if c.get("crane") else ""
            body = '<img src="%s"%s alt="Panel %s">' % (IMG[p["img"]], style, p["sub"])
        else:
            body = '<div class="empty"><span>no panel</span><span class="cost">5 cr</span></div>'
        plates.append('<div class="plate">%s<span class="sub">%s &middot; %s</span>%s</div>'
                      % (body, p["sub"], tc(p["at"]), overlay(c)))
    pcls = "plates two" if len(plates) > 1 else "plates"

    flag = ""
    if c.get("flag"):
        flag += '<p class="flag">%s</p>' % html.escape(c["flag"])
    if c.get("info"):
        flag += '<p class="flag info">%s</p>' % html.escape(c["info"])

    others = "".join('<option>%s</option>' % o["slate"]
                     for o in CELLS if o["slate"] != c["slate"])
    methods = "".join('<option%s>%s</option>' % (" selected" if m == c["method"] else "", m)
                      for m in ("generate", "composite", "split", "edit-only"))
    units = len(c["prompt"])

    return (
        '<article class="cell s-%s%s" data-slate="%s">'
        '<div class="strip">'
        '<span class="f"><b>SLATE</b><i>%s</i></span>'
        '<span class="f"><b>SECTION</b><i>%s</i></span>'
        '<span class="f"><b>SHOT SIZE</b><i>%s</i></span>'
        '<span class="f tc"><b>AT</b><i>%s</i></span>'
        '</div>'
        '<div class="frame"><span class="edge">%s</span>'
        '<div class="%s">%s</div>'
        '<span class="badge b-%s">%s</span>'
        '<span class="mth m-%s">%s</span></div>'
        '<div class="cap"><p class="hand">%s</p><p class="lyr">%s</p>%s</div>'
        '<div class="meta">'
        '<span><b>dur</b> <i class="num">%.3f s</i></span>'
        '<span><b>panels</b> <i class="num">%d</i></span>'
        '<span><b>move</b> <i>%s</i></span>'
        '<span><b>screen dir</b> <i>%s</i></span>'
        '</div>'
        '<details class="specs"%s>'
        '<summary data-mk="live" data-lbl="expand"><span class="sumo">Shot specs</span></summary>'
        '<div class="grid">'
        '<label class="fld sp2" data-mk="live" data-lbl="live counter">'
        '<span>Prompt sent to Runway</span>'
        '<textarea rows="4" data-count="%d">%s</textarea>'
        '<em class="cnt" id="cnt%d">%d / 1000 UTF-16 units</em></label>'
        '<label class="fld" data-mk="inert" data-lbl="no re-match"><span>Anchor line</span>'
        '<input type="text" value="%s"></label>'
        '<label class="fld" data-mk="inert" data-lbl="not wired">'
        '<span>Intended duration</span>'
        '<input type="text" class="num" value="%.3f"></label>'
        '<label class="fld" data-mk="inert" data-lbl="not wired"><span>Method</span>'
        '<select>%s</select></label>'
        '<div class="fld" data-mk="live" data-lbl="caps at 3">'
        '<span>Entities <em class="lim">max 3 refs</em></span>'
        '<div class="chips">%s</div></div>'
        '<div class="fld sp2" data-mk="live" data-lbl="works"><span>Swap panel with</span>'
        '<div class="swap"><select data-swapsel>%s</select>'
        '<button type="button" class="btn neu" data-swap>Swap</button></div></div>'
        '<div class="fld sp2 acts" data-mk="live" data-lbl="drives credits">'
        '<button type="button" class="btn ok" data-act="approve">Approve shot</button>'
        '<button type="button" class="btn warn" data-act="redraw">Redraw panel '
        '<span class="cost">5 cr</span></button>'
        '</div></div></details></article>'
        % (c["state"], " wide" if c.get("wide") else "", c["slate"],
           c["slate"], html.escape(c["section"]), html.escape(c["size"]), tc(c["start"]),
           html.escape(c["size"]), pcls, "".join(plates),
           c["state"], STATE_LABEL[c["state"]], c["method"], c["method"],
           html.escape(c["action"]), html.escape(c["lyric"]), flag,
           c["dur"], len(c["panels"]), html.escape(c["movement"]),
           html.escape(c["direction"]),
           " open" if c["expanded"] else "",
           i, html.escape(c["prompt"]), i, units,
           html.escape(c["lyric"].split(" / ")[0]), c["dur"], methods,
           ent_chips(c), others))


CELLS_HTML = "".join(cell_html(c, i) for i, c in enumerate(CELLS))

CAST_HTML = "".join(
    '<article class="ent-card">'
    '<div class="ent-plate"><img src="%s" alt="Reference plate for @%s"></div>'
    '<div class="ent-body">'
    '<div class="ent-top"><span class="tag">@%s</span><span class="kind">%s</span></div>'
    '<p class="ent-desc">%s</p>'
    '<div class="ent-foot"><span class="num">seed %s</span>'
    '<span class="num">%s</span><span class="lock">Locked</span>'
    '<button type="button" class="mini" data-mk="inert" data-lbl="not wired">Reroll</button>'
    '</div></div></article>'
    % (IMG[e["plate"]], e["tag"], e["tag"], e["kind"], html.escape(e["desc"]),
       e["seed"], e["cr"]) for e in ENTITIES)

tpl = (Path(__file__).resolve().parent / "board_tpl.html").read_text(encoding="utf-8")
for k, v in (("__CAST__", CAST_HTML), ("__CELLS__", CELLS_HTML),
             ("__BLOCKS__", "".join(BLOCKS)), ("__SECS__", "".join(SECS)),
             ("__TICKS__", TICKS), ("__SHOTS__", SHOTS_JS),
             ("__VIDEO__", VIDEO), ("__POSTER__", IMG["C_composed"]),
             ("__DROPIMG__", IMG["D_face"])):
    tpl = tpl.replace(k, v)

OUT.write_text(tpl, encoding="utf-8")
print("wrote %s  %.2f MB" % (OUT, OUT.stat().st_size / 1048576))
print("timeline blocks:", len(BLOCKS), "| ticks:", len(dbs), "| cells:", len(CELLS))
print("span %.3f s  sum of extents %.3f s" % (SPAN, sum(b["dur"] for b in TL)))
