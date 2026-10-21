#!/usr/bin/env python3
"""
Builds assets/dashboard.svg for the ADVRMA profile README.

Runs inside GitHub Actions (see .github/workflows/snake.yml). It reads public
profile data through GitHub's GraphQL API with the workflow's own token, so no
outside stats service is needed and nothing can rate-limit it.

  python scripts/dashboard.py              # live data (needs GH_TOKEN)
  python scripts/dashboard.py --mock       # fake data, for local previews
  python scripts/dashboard.py --placeholder
"""
import datetime as dt
import json
import math
import os
import random
import sys
import urllib.request
from xml.sax.saxutils import escape as esc

USER = os.environ.get("GH_USER", "ADVRMA")
OUT = os.environ.get("DASHBOARD_OUT", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "dashboard.svg"))

BG, PANEL, LINE = "#0B0F14", "#0F161D", "#1E2A22"
LIME, LIME2, CYAN, VIOLET = "#A3E635", "#84CC16", "#22D3EE", "#A78BFA"
TEXT, MUTED = "#E6EDF3", "#8B949E"
SANS = "'Segoe UI', Inter, -apple-system, BlinkMacSystemFont, 'Helvetica Neue', Arial, sans-serif"
MONO = "'JetBrains Mono', 'SF Mono', 'Cascadia Code', Consolas, 'Liberation Mono', monospace"
LEVELS = ["#161B22", "#1A3B0F", "#3F6212", "#65A30D", "#A3E635"]

# ----------------------------------------------------------------------------- data
API = "https://api.github.com/graphql"
Q_MAIN = """
query($login: String!) {
  user(login: $login) {
    createdAt
    followers { totalCount }
    repositories(ownerAffiliations: OWNER, isFork: false, first: 100, privacy: PUBLIC) {
      totalCount
      nodes {
        stargazerCount
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
    contributionsCollection {
      totalCommitContributions
      restrictedContributionsCount
      totalPullRequestContributions
      totalIssueContributions
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}"""
Q_YEAR = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar { weeks { contributionDays { date contributionCount } } }
    }
  }
}"""


def gql(query, variables):
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit("GH_TOKEN is not set")
    req = urllib.request.Request(API, data=json.dumps({"query": query, "variables": variables}).encode(),
                                 headers={"Authorization": f"bearer {token}", "Content-Type": "application/json",
                                          "User-Agent": "profile-dashboard"})
    with urllib.request.urlopen(req, timeout=30) as r:
        payload = json.load(r)
    if payload.get("errors"):
        sys.exit("GraphQL error: " + json.dumps(payload["errors"])[:500])
    return payload["data"]


def fetch():
    u = gql(Q_MAIN, {"login": USER})["user"]
    cc = u["contributionsCollection"]
    weeks = [[(d["date"], d["contributionCount"]) for d in w["contributionDays"]] for w in cc["contributionCalendar"]["weeks"]]

    # full history for streaks (one request per calendar year since the account was created)
    days = {}
    start_year = int(u["createdAt"][:4])
    now = dt.datetime.now(dt.timezone.utc)
    for y in range(start_year, now.year + 1):
        frm = f"{y}-01-01T00:00:00Z"
        to = f"{y}-12-31T23:59:59Z" if y < now.year else now.strftime("%Y-%m-%dT%H:%M:%SZ")
        cal = gql(Q_YEAR, {"login": USER, "from": frm, "to": to})["user"]["contributionsCollection"]["contributionCalendar"]
        for w in cal["weeks"]:
            for d in w["contributionDays"]:
                days[d["date"]] = d["contributionCount"]
    for w in weeks:
        for date, c in w:
            days[date] = c

    langs = {}
    stars = 0
    for repo in u["repositories"]["nodes"]:
        stars += repo["stargazerCount"]
        for e in repo["languages"]["edges"]:
            n = e["node"]["name"]
            langs.setdefault(n, [0, e["node"]["color"] or MUTED])
            langs[n][0] += e["size"]

    return {
        "weeks": weeks,
        "days": days,
        "total_year": cc["contributionCalendar"]["totalContributions"],
        "commits": cc["totalCommitContributions"] + cc["restrictedContributionsCount"],
        "prs": cc["totalPullRequestContributions"],
        "issues": cc["totalIssueContributions"],
        "repos": u["repositories"]["totalCount"],
        "stars": stars,
        "followers": u["followers"]["totalCount"],
        "langs": langs,
    }


def mock():
    random.seed(4)
    today = dt.date(2026, 10, 21)
    start = today - dt.timedelta(days=today.weekday() + 1 + 52 * 7)  # a Sunday
    weeks, days = [], {}
    d = start
    while d <= today:
        week = []
        for _ in range(7):
            if d > today:
                break
            active = 0.08 if d.month < 6 else (0.45 if d.month in (7, 8) else 0.3)
            c = random.choice([1, 1, 2, 3, 4, 6, 9]) if random.random() < active else 0
            if today - d < dt.timedelta(days=5):
                c = random.randint(1, 5)
            week.append((d.isoformat(), c)); days[d.isoformat()] = c
            d += dt.timedelta(days=1)
        weeks.append(week)
    return {"weeks": weeks, "days": days, "total_year": sum(days.values()), "commits": 130, "prs": 3, "issues": 1,
            "repos": 24, "stars": 5, "followers": 18,
            "langs": {"TypeScript": [402500, "#3178c6"], "JavaScript": [303600, "#f1e05a"], "Java": [132900, "#b07219"],
                      "CSS": [127300, "#563d7c"], "HTML": [19100, "#e34c26"], "Python": [14500, "#3572A5"], "Swift": [9000, "#F05138"]}}


def streaks(days):
    dates = sorted(days)
    if not dates:
        return (0, None, None), (0, None, None)
    best, run, run_start = (0, None, None), 0, None
    for ds in dates:
        if days[ds] > 0:
            if run == 0:
                run_start = ds
            run += 1
            if run > best[0]:
                best = (run, run_start, ds)
        else:
            run = 0
    # current: walk back from today (today may still be 0 without breaking the streak)
    i = len(dates) - 1
    if days[dates[i]] == 0:
        i -= 1
    cur, end = 0, dates[i] if i >= 0 else None
    while i >= 0 and days[dates[i]] > 0:
        cur += 1; i -= 1
    cur_start = dates[i + 1] if cur else None
    return (cur, cur_start, end if cur else None), best


def fmt_range(a, b):
    if not a:
        return "start one today"
    fa = dt.date.fromisoformat(a); fb = dt.date.fromisoformat(b)
    f = lambda d: d.strftime("%b ") + str(d.day)
    return f(fa) if a == b else f"{f(fa)} – {f(fb)}"


# ----------------------------------------------------------------------------- drawing helpers
def shade(hexc, k):
    h = hexc.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return "#%02X%02X%02X" % tuple(max(0, min(255, int(v * k))) for v in (r, g, b))


def count_up(x, y, value, size, anchor="start", suffix="", begin=0.25, color=TEXT, frames=14, dur=1.1):
    """Number that ticks up from 0 using discrete frames (pure SMIL, works on GitHub)."""
    out = []
    for i in range(frames + 1):
        t = i / frames
        v = round(value * (1 - (1 - t) ** 3))
        t0 = begin + dur * i / frames
        t1 = begin + dur * (i + 1) / frames
        hide = "" if i == frames else f'<set attributeName="visibility" to="hidden" begin="{t1:.2f}s" fill="freeze"/>'
        vis = "visible" if i == 0 else "hidden"
        show = "" if i == 0 else f'<set attributeName="visibility" to="visible" begin="{t0:.2f}s" fill="freeze"/>'
        out.append(f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-family="{SANS}" font-size="{size}" font-weight="800" '
                   f'fill="{color}" visibility="{vis}" letter-spacing="-0.5">{v:,}<tspan font-size="{size*0.45:.0f}" fill="{MUTED}" '
                   f'font-weight="600" dx="6">{esc(suffix)}</tspan>{show}{hide}</text>')
    return "".join(out)


def sweep(x, y, w, h, r, dur, begin=0.0, opacity=0.85):
    per = 2 * (w + h - 4 * r) + 2 * math.pi * r
    seg = per * 0.16
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="none" stroke="url(#sweep)" stroke-width="1.6" '
            f'stroke-linecap="round" opacity="{opacity}" stroke-dasharray="{seg:.1f} {per-seg:.1f}">'
            f'<animate attributeName="stroke-dashoffset" from="0" to="{-per:.1f}" dur="{dur}s" begin="{begin}s" repeatCount="indefinite"/></rect>')


def icon(kind, col):
    if kind == "bolt":
        return f'<path d="M22 6 L11 22 H19 L17 34 L29 17 H21 Z" fill="{col}"/>'
    if kind == "flame":
        return (f'<path d="M20 6 C26 13 30 17 30 24 A10 10 0 0 1 10 24 C10 19 13 16 15 13 C16 17 18 18 19 18 C19 13 18 10 20 6 Z" fill="{col}">'
                f'<animateTransform attributeName="transform" type="scale" values="1 1;1 1.06;1 1" additive="sum" dur="1.2s" repeatCount="indefinite"/></path>')
    if kind == "trophy":
        return (f'<path d="M12 8 H28 V16 A8 8 0 0 1 12 16 Z" fill="{col}"/><path d="M12 10 H7 A5 5 0 0 0 12 18 M28 10 H33 A5 5 0 0 1 28 18" fill="none" stroke="{col}" stroke-width="2"/>'
                f'<rect x="18" y="23" width="4" height="6" fill="{col}"/><rect x="13" y="29" width="14" height="4" rx="1.5" fill="{col}"/>')
    if kind == "commit":
        return (f'<line x1="4" y1="20" x2="36" y2="20" stroke="{col}" stroke-width="2.4"/>'
                f'<circle cx="20" cy="20" r="7" fill="{PANEL}" stroke="{col}" stroke-width="2.6"/>')
    return ""


# ----------------------------------------------------------------------------- render
def render(data, updated):
    W, H = 1200, 452
    o = [f'''<defs>
<linearGradient id="sweep" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{LIME}"/><stop offset="0.5" stop-color="{CYAN}"/><stop offset="1" stop-color="{LIME}"/></linearGradient>
<filter id="glow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="5" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
<radialGradient id="cityglow" cx="0.5" cy="0.75" r="0.6"><stop offset="0" stop-color="{LIME}" stop-opacity="0.16"/><stop offset="1" stop-color="{LIME}" stop-opacity="0"/></radialGradient>
<linearGradient id="floor" x1="0" x2="1"><stop offset="0" stop-color="{PANEL}" stop-opacity="1"/><stop offset="0.06" stop-color="{PANEL}" stop-opacity="0"/><stop offset="0.94" stop-color="{PANEL}" stop-opacity="0"/><stop offset="1" stop-color="{PANEL}" stop-opacity="1"/></linearGradient>
</defs>''']

    (cur, cs, ce), (best, bs, be) = streaks(data["days"])
    tiles = [
        ("bolt", LIME, "CONTRIBUTIONS", data["total_year"], "", "in the past year"),
        ("flame", "#FB923C", "CURRENT STREAK", cur, "days" if cur != 1 else "day", fmt_range(cs, ce)),
        ("trophy", "#FACC15", "LONGEST STREAK", best, "days" if best != 1 else "day", fmt_range(bs, be)),
        ("commit", CYAN, "COMMITS", data["commits"], "", f'{data["prs"]} PRs · {data["repos"]} repos · {data["stars"]} ★'),
    ]
    tw, th, gap = 288, 118, 16
    for i, (ic, col, label, val, suf, sub) in enumerate(tiles):
        x = i * (tw + gap)
        o.append(f'<g transform="translate({x},0)" opacity="0"><animate attributeName="opacity" values="0;1" dur="0.5s" begin="{0.08*i:.2f}s" fill="freeze"/>'
                 f'<animateTransform attributeName="transform" type="translate" values="{x} 10;{x} 0" dur="0.5s" begin="{0.08*i:.2f}s" fill="freeze"/>')
        o.append(f'<rect x="1" y="1" width="{tw-2}" height="{th-2}" rx="16" fill="{PANEL}" stroke="{LINE}" stroke-width="1.5"/>')
        o.append(f'<rect x="1" y="1" width="{tw-2}" height="{th-2}" rx="16" fill="{col}" fill-opacity="0.035"/>')
        o.append(f'<g transform="translate(22,22)"><rect width="40" height="40" rx="11" fill="{col}" fill-opacity="0.13" stroke="{col}" stroke-opacity="0.4"/>{icon(ic, col)}</g>')
        o.append(f'<text x="76" y="38" font-family="{MONO}" font-size="11.5" letter-spacing="1.8" fill="{MUTED}">{label}</text>')
        o.append(count_up(76, 78, val, 34, suffix=suf, begin=0.35 + 0.1 * i))
        o.append(f'<text x="24" y="{th-16}" font-family="{SANS}" font-size="13" fill="{MUTED}">{esc(sub)}</text>')
        if ic == "flame":  # progress ring: current vs longest
            frac = 0 if best == 0 else min(1, cur / best)
            r = 22; C = 2 * math.pi * r; L = C * frac
            o.append(f'<g transform="translate({tw-48},50)"><circle r="{r}" fill="none" stroke="#1C2530" stroke-width="5"/>'
                     f'<circle r="{r}" fill="none" stroke="{col}" stroke-width="5" stroke-linecap="round" transform="rotate(-90)" '
                     f'stroke-dasharray="{L:.1f} {C:.1f}" stroke-dashoffset="{L:.1f}" filter="url(#glow)">'
                     f'<animate attributeName="stroke-dashoffset" values="{L:.1f};0" dur="1.2s" begin="0.5s" fill="freeze" calcMode="spline" keyTimes="0;1" keySplines="0.3 0 0.2 1"/></circle>'
                     f'<text y="4.5" text-anchor="middle" font-family="{MONO}" font-size="12" fill="{TEXT}">{round(frac*100)}%</text></g>')
        o.append(sweep(1, 1, tw - 2, th - 2, 16, dur=7, begin=-1.7 * i, opacity=0.7))
        o.append('</g>')

    # ---------------- contribution city (isometric)
    py, ph = th + 18, H - th - 18
    cw = 760
    o.append(f'<g transform="translate(0,{py})">')
    o.append(f'<rect x="1" y="1" width="{cw-2}" height="{ph-2}" rx="18" fill="{PANEL}" stroke="{LINE}" stroke-width="1.5"/>')
    o.append(f'<rect x="1" y="1" width="{cw-2}" height="{ph-2}" rx="18" fill="url(#cityglow)"/>')
    o.append(f'<text x="26" y="38" font-family="{SANS}" font-size="19" font-weight="800" fill="{TEXT}">Contribution City</text>')
    o.append(f'<text x="26" y="58" font-family="{MONO}" font-size="11.5" fill="{MUTED}" letter-spacing="0.5">last 12 months · updated {esc(updated)}</text>')
    # legend
    lx = cw - 26 - 5 * 16 - 70
    o.append(f'<text x="{lx}" y="{ph-18}" font-family="{MONO}" font-size="11" fill="{MUTED}">less</text>')
    for k, c in enumerate(LEVELS):
        o.append(f'<rect x="{lx + 34 + k*16}" y="{ph-28}" width="12" height="12" rx="3" fill="{c}"/>')
    o.append(f'<text x="{lx + 34 + 5*16 + 4}" y="{ph-18}" font-family="{MONO}" font-size="11" fill="{MUTED}">more</text>')

    weeks = data["weeks"][-53:]
    counts = [c for w in weeks for _, c in w]
    mx = max(counts) if counts and max(counts) > 0 else 1
    nz = sorted(c for c in counts if c > 0)
    def level(c):
        if c == 0:
            return 0
        if not nz:
            return 1
        q = [nz[int(len(nz) * f)] for f in (0.25, 0.5, 0.75)]
        return 1 + sum(c > t for t in q)
    WV, DV, HMAX, S = (12.2, -1.8), (7.0, 6.2), 64, 0.8
    ox, oy = 34, 236
    def P(w, d, h=0.0):
        return (ox + w * WV[0] + d * DV[0], oy + w * WV[1] + d * DV[1] - h)
    def poly(pts):
        return " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    peak = None
    o.append(f'<g transform="translate(0,0)">')
    for wi in range(len(weeks) - 1, -1, -1):
        for di, (date, c) in enumerate(weeks[wi]):
            dd = dt.date.fromisoformat(date).isoweekday() % 7  # Sunday=0
            lv = level(c)
            col = LEVELS[lv]
            a = P(wi, dd); b = P(wi + S, dd); dpt = P(wi, dd + S); e = P(wi + S, dd + S)
            if c == 0:
                o.append(f'<polygon points="{poly([a, b, e, dpt])}" fill="{col}"/>')
                continue
            h = max(5.0, HMAX * (c / mx) ** 0.65)
            top = lambda hh: [P(wi, dd, hh), P(wi + S, dd, hh), P(wi + S, dd + S, hh), P(wi, dd + S, hh)]
            left = lambda hh: [a, dpt, P(wi, dd + S, hh), P(wi, dd, hh)]
            front = lambda hh: [dpt, e, P(wi + S, dd + S, hh), P(wi, dd + S, hh)]
            bgn = 0.6 + wi * 0.028
            anim = lambda f: (f'<animate attributeName="points" values="{poly(f(0))};{poly(f(h))}" dur="0.7s" begin="{bgn:.2f}s" '
                              f'fill="freeze" calcMode="spline" keyTimes="0;1" keySplines="0.2 0.8 0.2 1"/>')
            o.append(f'<polygon points="{poly(left(0))}" fill="{shade(col, 0.55)}">{anim(left)}</polygon>')
            o.append(f'<polygon points="{poly(front(0))}" fill="{shade(col, 0.75)}">{anim(front)}</polygon>')
            o.append(f'<polygon points="{poly(top(0))}" fill="{col}">{anim(top)}</polygon>')
            if peak is None or c > peak[0]:
                peak = (c, P(wi + S / 2, dd + S / 2, h), date, bgn)
    o.append('</g>')
    if peak:
        c, (x, y), date, bgn = peak
        ly = max(66.0, y - 48)
        x = min(max(x, 80), cw - 80)
        o.append(f'<g opacity="0"><animate attributeName="opacity" values="0;1" dur="0.4s" begin="{bgn+0.7:.2f}s" fill="freeze"/>'
                 f'<line x1="{x:.1f}" y1="{y-4:.1f}" x2="{x:.1f}" y2="{ly+22:.1f}" stroke="{LIME}" stroke-width="1.2" stroke-dasharray="2 3"/>'
                 f'<circle cx="{x:.1f}" cy="{y-2:.1f}" r="3" fill="{LIME}" filter="url(#glow)"><animate attributeName="r" values="2.5;4.5;2.5" dur="1.6s" repeatCount="indefinite"/></circle>'
                 f'<rect x="{x-56:.1f}" y="{ly:.1f}" width="112" height="22" rx="11" fill="#0A1209" stroke="{LIME}" stroke-opacity="0.5"/>'
                 f'<text x="{x:.1f}" y="{ly+15:.1f}" text-anchor="middle" font-family="{MONO}" font-size="11" fill="{TEXT}">peak · {c} on {dt.date.fromisoformat(date).strftime("%b")} {dt.date.fromisoformat(date).day}</text></g>')
    # month labels along the front edge
    prev, last_wi = None, -9
    for wi, w in enumerate(weeks):
        m = dt.date.fromisoformat(w[0][0]).strftime("%b")
        if prev is not None and m != prev and wi - last_wi >= 4:
            x, y = P(wi, 7.4)
            o.append(f'<text x="{x:.1f}" y="{y+12:.1f}" font-family="{MONO}" font-size="10.5" fill="{MUTED}" opacity="0.75">{m}</text>')
            last_wi = wi
        prev = m
    o.append(sweep(1, 1, cw - 2, ph - 2, 18, dur=11, opacity=0.6))
    o.append('</g>')

    # ---------------- languages
    lx0, lw = cw + 16, W - cw - 16
    total = sum(v[0] for v in data["langs"].values()) or 1
    top = sorted(data["langs"].items(), key=lambda kv: -kv[1][0])[:6]
    tmax = top[0][1][0] if top else 1
    o.append(f'<g transform="translate({lx0},{py})">')
    o.append(f'<rect x="1" y="1" width="{lw-2}" height="{ph-2}" rx="18" fill="{PANEL}" stroke="{LINE}" stroke-width="1.5"/>')
    o.append(f'<text x="24" y="38" font-family="{SANS}" font-size="19" font-weight="800" fill="{TEXT}">Top Languages</text>')
    o.append(f'<text x="24" y="58" font-family="{MONO}" font-size="11.5" fill="{MUTED}" letter-spacing="0.5">by bytes across public repos</text>')
    bx, by, bw = 24, 78, lw - 48
    o.append(f'<clipPath id="barclip"><rect x="{bx}" y="{by}" width="{bw}" height="12" rx="6"/></clipPath>')
    o.append(f'<rect x="{bx}" y="{by}" width="{bw}" height="12" rx="6" fill="#1C2530"/><g clip-path="url(#barclip)">')
    acc = 0
    for i, (name, (size, col)) in enumerate(top):
        seg = bw * size / total
        o.append(f'<rect x="{bx+acc:.1f}" y="{by}" width="0" height="12" fill="{col}">'
                 f'<animate attributeName="width" values="0;{seg:.1f}" dur="0.6s" begin="{0.5+i*0.12:.2f}s" fill="freeze"/></rect>')
        acc += seg
    o.append('</g>')
    for i, (name, (size, col)) in enumerate(top):
        y = 120 + i * 27
        pct = 100 * size / total
        o.append(f'<g opacity="0"><animate attributeName="opacity" values="0;1" dur="0.4s" begin="{0.6+i*0.1:.2f}s" fill="freeze"/>'
                 f'<circle cx="{bx+6}" cy="{y-4}" r="5.5" fill="{col}"/>'
                 f'<text x="{bx+20}" y="{y}" font-family="{SANS}" font-size="14.5" font-weight="600" fill="{TEXT}">{esc(name)}</text>'
                 f'<rect x="{bx+130}" y="{y-8}" width="{bw-130-58}" height="6" rx="3" fill="#1C2530"/>'
                 f'<rect x="{bx+130}" y="{y-8}" width="0" height="6" rx="3" fill="{col}">'
                 f'<animate attributeName="width" values="0;{(bw-130-58)*size/tmax:.1f}" dur="0.8s" begin="{0.7+i*0.1:.2f}s" fill="freeze" calcMode="spline" keyTimes="0;1" keySplines="0.3 0 0.2 1"/></rect>'
                 f'<text x="{bx+bw}" y="{y}" text-anchor="end" font-family="{MONO}" font-size="12.5" fill="{MUTED}">{pct:.1f}%</text></g>')
    o.append(f'<line x1="24" x2="{lw-24}" y1="{ph-44}" y2="{ph-44}" stroke="{LINE}"/>')
    o.append(f'<text x="24" y="{ph-20}" font-family="{MONO}" font-size="12" fill="{MUTED}">'
             f'<tspan fill="{LIME}">●</tspan> {data["repos"]} repos   <tspan fill="#FACC15">★</tspan> {data["stars"]} stars   '
             f'<tspan fill="{CYAN}">◆</tspan> {data["followers"]} followers</text>')
    o.append(sweep(1, 1, lw - 2, ph - 2, 18, dur=9, begin=-3, opacity=0.6))
    o.append('</g>')

    body = "\n".join(o)
    label = f"GitHub dashboard for {USER}: {data['total_year']} contributions in the past year, {cur}-day current streak, {best}-day longest streak"
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="{esc(label)}">'
            f'<title>{esc(label)}</title>\n{body}\n</svg>\n')


def placeholder():
    W, H = 1200, 452
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="Dashboard is building">
<rect x="1" y="1" width="{W-2}" height="{H-2}" rx="18" fill="{PANEL}" stroke="{LINE}" stroke-width="1.5"/>
<g transform="translate({W/2},{H/2-20})"><circle r="26" fill="none" stroke="#1C2530" stroke-width="5"/>
<circle r="26" fill="none" stroke="{LIME}" stroke-width="5" stroke-linecap="round" stroke-dasharray="40 200">
<animateTransform attributeName="transform" type="rotate" from="0" to="360" dur="1.2s" repeatCount="indefinite"/></circle></g>
<text x="{W/2}" y="{H/2+44}" text-anchor="middle" font-family="{SANS}" font-size="20" font-weight="700" fill="{TEXT}">Building live dashboard…</text>
<text x="{W/2}" y="{H/2+70}" text-anchor="middle" font-family="{MONO}" font-size="13" fill="{MUTED}">appears after the first workflow run</text>
</svg>
'''


if __name__ == "__main__":
    os.makedirs(os.path.dirname(os.path.abspath(OUT)), exist_ok=True)
    if "--placeholder" in sys.argv:
        svg = placeholder()
    else:
        data = mock() if "--mock" in sys.argv else fetch()
        svg = render(data, dt.datetime.now(dt.timezone.utc).strftime("%b %d, %Y"))
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"wrote {OUT} ({len(svg)//1024} KB)")
