"""Genera tarjetas SVG con estadísticas de GitHub usando la API GraphQL.

Sin dependencias externas: solo librería estándar de Python.
Variables de entorno: GITHUB_TOKEN, USERNAME. Salida: carpeta stats/.
"""
import json
import os
import sys
import urllib.request
from datetime import date, timedelta
from html import escape

OUT_DIR = "stats"

# Paleta (tokyonight)
BG = "#1a1b27"
BORDER = "#2a2e3f"
TITLE = "#70a5fd"
TEXT = "#c0caf5"
MUTED = "#8b92b8"
ACCENT = "#bf91f3"
ICON = "#38bdae"

QUERY = """
query($login: String!) {
  user(login: $login) {
    name
    login
    followers { totalCount }
    pullRequests { totalCount }
    issues { totalCount }
    repositories(first: 100, ownerAffiliations: OWNER, isFork: false,
                 orderBy: {field: UPDATED_AT, direction: DESC}) {
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
      contributionCalendar {
        totalContributions
        weeks { contributionDays { contributionCount date } }
      }
    }
  }
}
"""


def fetch(login, token):
    body = json.dumps({"query": QUERY, "variables": {"login": login}}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        data = json.load(resp)
    if "errors" in data:
        sys.exit(f"Error de la API: {data['errors']}")
    return data["data"]["user"]


def streaks(days):
    """Devuelve (racha actual, racha más larga) en días."""
    counts = {d["date"]: d["contributionCount"] for d in days}
    ordered = sorted(counts)
    longest = run = 0
    for d in ordered:
        run = run + 1 if counts[d] > 0 else 0
        longest = max(longest, run)
    # Racha actual: si hoy aún no hay contribuciones, se cuenta desde ayer
    current = 0
    day = date.fromisoformat(ordered[-1])
    if counts.get(day.isoformat(), 0) == 0:
        day -= timedelta(days=1)
    while counts.get(day.isoformat(), 0) > 0:
        current += 1
        day -= timedelta(days=1)
    return current, longest


def card(width, height, title, inner):
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <style>
    .t {{ font: 600 18px 'Segoe UI', Ubuntu, sans-serif; fill: {TITLE}; }}
    .l {{ font: 400 14px 'Segoe UI', Ubuntu, sans-serif; fill: {TEXT}; }}
    .v {{ font: 700 14px 'Segoe UI', Ubuntu, sans-serif; fill: {ACCENT}; }}
    .s {{ font: 400 12px 'Segoe UI', Ubuntu, sans-serif; fill: {MUTED}; }}
    .big {{ font: 700 28px 'Segoe UI', Ubuntu, sans-serif; fill: {ACCENT}; }}
    .row {{ opacity: 0; animation: in .5s ease forwards; }}
    @keyframes in {{ from {{ opacity: 0; transform: translateX(-8px); }} to {{ opacity: 1; transform: none; }} }}
    @keyframes grow {{ from {{ transform: scaleX(0); }} to {{ transform: scaleX(1); }} }}
    .bar {{ transform-origin: left; animation: grow .9s ease-out forwards; }}
  </style>
  <rect x="0.5" y="0.5" rx="8" width="{width - 1}" height="{height - 1}" fill="{BG}" stroke="{BORDER}"/>
  <text x="25" y="35" class="t">{escape(title)}</text>
{inner}
</svg>
"""


def stats_card(u):
    repos = u["repositories"]["nodes"]
    cc = u["contributionsCollection"]
    days = [d for w in cc["contributionCalendar"]["weeks"] for d in w["contributionDays"]]
    current, longest = streaks(days)
    rows = [
        ("⭐", "Estrellas recibidas", sum(r["stargazerCount"] for r in repos)),
        ("📝", "Commits (último año)", cc["totalCommitContributions"] + cc["restrictedContributionsCount"]),
        ("🔀", "Pull requests", u["pullRequests"]["totalCount"]),
        ("🐞", "Issues", u["issues"]["totalCount"]),
        ("📦", "Repositorios", u["repositories"]["totalCount"]),
        ("👥", "Seguidores", u["followers"]["totalCount"]),
    ]
    inner = []
    for i, (icon, label, value) in enumerate(rows):
        y = 70 + i * 28
        inner.append(
            f'  <g class="row" style="animation-delay:{0.1 * i:.1f}s">'
            f'<text x="25" y="{y}" class="l">{icon}  {escape(label)}</text>'
            f'<text x="255" y="{y}" class="v">{value}</text></g>'
        )
    # Bloque de racha y contribuciones a la derecha
    total = cc["contributionCalendar"]["totalContributions"]
    blocks = [("Contribuciones (12 meses)", total), ("Racha actual (días)", current), ("Mejor racha (días)", longest)]
    for i, (label, value) in enumerate(blocks):
        x = 340
        y = 80 + i * 55
        inner.append(
            f'  <g class="row" style="animation-delay:{0.3 + 0.15 * i:.2f}s">'
            f'<text x="{x}" y="{y}" class="big">{value}</text>'
            f'<text x="{x}" y="{y + 18}" class="s">{escape(label)}</text></g>'
        )
    inner.append(f'  <line x1="320" y1="55" x2="320" y2="220" stroke="{BORDER}"/>')
    return card(520, 240, "📊 Estadísticas de GitHub", "\n".join(inner))


def languages_card(u):
    totals, colors = {}, {}
    for r in u["repositories"]["nodes"]:
        for e in r["languages"]["edges"]:
            name = e["node"]["name"]
            totals[name] = totals.get(name, 0) + e["size"]
            colors[name] = e["node"]["color"] or MUTED
    top = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:8]
    grand = sum(v for _, v in top) or 1
    inner = []
    # Barra apilada
    x = 25.0
    bar_w = 470
    inner.append(f'  <clipPath id="c"><rect x="25" y="55" width="{bar_w}" height="10" rx="5"/></clipPath>')
    inner.append('  <g clip-path="url(#c)" class="bar">')
    for name, size in top:
        w = bar_w * size / grand
        inner.append(f'    <rect x="{x:.2f}" y="55" width="{w:.2f}" height="10" fill="{colors[name]}"/>')
        x += w
    inner.append("  </g>")
    # Leyenda en dos columnas
    for i, (name, size) in enumerate(top):
        col, row = i % 2, i // 2
        lx, ly = 25 + col * 245, 95 + row * 26
        pct = 100 * size / grand
        inner.append(
            f'  <g class="row" style="animation-delay:{0.4 + 0.08 * i:.2f}s">'
            f'<circle cx="{lx + 5}" cy="{ly - 5}" r="5" fill="{colors[name]}"/>'
            f'<text x="{lx + 18}" y="{ly}" class="l">{escape(name)}</text>'
            f'<text x="{lx + 215}" y="{ly}" class="s" text-anchor="end">{pct:.1f}%</text></g>'
        )
    height = 95 + ((len(top) + 1) // 2) * 26
    return card(520, max(height, 140), "💻 Lenguajes más usados", "\n".join(inner))


def main():
    token = os.environ.get("GITHUB_TOKEN")
    login = os.environ.get("USERNAME")
    if not token or not login:
        sys.exit("Faltan GITHUB_TOKEN o USERNAME")
    user = fetch(login, token)
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(f"{OUT_DIR}/stats.svg", "w", encoding="utf-8") as f:
        f.write(stats_card(user))
    with open(f"{OUT_DIR}/languages.svg", "w", encoding="utf-8") as f:
        f.write(languages_card(user))
    print("Tarjetas generadas en", OUT_DIR)


if __name__ == "__main__":
    main()
