"""Regenerate the two live pieces of the profile README.

Both are derived from GitHub's own API rather than hand-typed, because a
hand-typed number on a profile is only true on the day it is typed.

  1. The commit-time table  -> written between markers in README.md
  2. pop.svg                -> the contribution grid, popping cell by cell

Run with a token in GH_TOKEN. A token with `repo` scope counts private
contributions too; the workflow's default GITHUB_TOKEN sees only public ones,
which is a smaller number, not a wrong one.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

USER = "Vanshcloud"
# Commit timestamps come back from the API normalised to UTC, so the buckets
# would describe a machine in London rather than a person in Delhi.
LOCAL = timezone(timedelta(hours=5, minutes=30))
ROOT = Path(__file__).resolve().parent.parent

BUCKETS = (
    ("🌞 Morning", 6, 12),
    ("🌆 Daytime", 12, 18),
    ("🌃 Evening", 18, 24),
    ("🌙 Night", 0, 6),
)


def run(cmd: list[str], what: str) -> str:
    """A `gh` call whose failure says what GitHub actually objected to.

    subprocess's own CalledProcessError prints the command and the exit code
    and drops stderr on the floor, which turns "your token is missing a scope"
    into "exit status 1" — a message that costs an hour to act on.
    """
    done = subprocess.run(cmd, capture_output=True, text=True)
    if done.returncode != 0:
        sys.exit(f"{what} failed:\n{(done.stderr or done.stdout).strip()}")
    return done.stdout


def gh(path: str, paginate: bool = False) -> object:
    """One `gh api` call. gh is already on the runner and already authed."""
    cmd = ["gh", "api", path]
    if paginate:
        # --slurp keeps each page a separate array instead of concatenating
        # them into invalid JSON, which is what plain --paginate emits.
        cmd.append("--paginate")
        cmd.append("--slurp")
    parsed = json.loads(run(cmd, f"GET {path}"))
    if paginate:
        return [item for page in parsed for item in page]
    return parsed


def commit_hours() -> tuple[Counter, bool]:
    """Every commit this user authored, bucketed by local hour."""
    # /user/repos is the only listing that includes this account's private
    # repositories — users/<login>/repos returns 5 of the 10 even when the
    # request is authenticated as that very user.
    try:
        repos = gh("user/repos?per_page=100&affiliation=owner", paginate=True)
    except subprocess.CalledProcessError:
        repos = gh(f"users/{USER}/repos?per_page=100", paginate=True)
    # Which endpoint answered says nothing about what came back: a workflow's
    # default GITHUB_TOKEN calls /user/repos quite happily and is simply handed
    # the public subset, no error raised. Whether a private repository is in
    # the response is the only honest signal.
    private = any(repo["private"] for repo in repos)
    names = {r["full_name"] for r in repos if not r["fork"]}
    hours: Counter = Counter()
    for full_name in sorted(names):
        try:
            commits = gh(f"repos/{full_name}/commits?per_page=100", paginate=True)
        except subprocess.CalledProcessError as failure:
            # An empty repository answers 409 and has nothing to count. Every
            # other failure — a rate limit above all — must not be swallowed:
            # skipping a repository silently publishes a smaller number that
            # looks exactly as authoritative as the real one.
            if "409" in (failure.stderr or "") or "Git Repository is empty" in (
                failure.stderr or ""
            ):
                continue
            sys.exit(f"could not read commits for {full_name}: {failure.stderr}")
        for commit in commits:
            author = commit.get("author") or {}
            if author.get("login") != USER:
                continue
            stamp = datetime.strptime(
                commit["commit"]["author"]["date"], "%Y-%m-%dT%H:%M:%SZ"
            ).replace(tzinfo=timezone.utc)
            hours[stamp.astimezone(LOCAL).hour] += 1
    scope = "private included" if private else "public only, no GH_PAT"
    print(f"scanned {len(names)} repos ({scope}): {sum(hours.values())} commits")
    return hours, private


def commit_table(hours: Counter, private: bool) -> str:
    counts = [
        (label, sum(hours[h] for h in range(start, end)))
        for label, start, end in BUCKETS
    ]
    total = sum(count for _, count in counts) or 1
    width = 25
    lines = []
    for index, (label, count) in enumerate(counts, start=1):
        share = count / total
        filled = round(share * width)
        bar = "█" * filled + "░" * (width - filled)
        lines.append(f"{index}  {label:<12}{count:>5} commits   {bar}   {share * 100:>5.1f}%")

    morning = counts[0][1] + counts[1][1]
    night = counts[2][1] + counts[3][1]
    title = "I'm a Night 🦉" if night > morning else "I'm an early 🐤"
    # A run without a PAT counts a strict subset of the commits. Saying which
    # subset beats publishing the smaller number as though it were the whole.
    note = "" if private else (
        "<br><sub>Counted across public repositories only — set a "
        "<code>GH_PAT</code> secret to include private commits.</sub>"
    )
    # A ``` fence would render the full width of the page and carry GitHub's
    # copy button. A <pre> in a one-cell table shrinks to its content and gets
    # neither, while still holding the column alignment the bars depend on.
    # align="center" on the table rather than a wrapping <div align="center">:
    # GitHub styles markdown tables display:block;width:max-content, which
    # text-align does not centre, and inline styles are stripped. Centring the
    # <pre> instead would centre each line and destroy the column alignment.
    # No blank lines inside the HTML block, or GitHub drops back into markdown
    # mode partway through and renders the tags as text.
    body = "\n".join(lines)
    return (
        '<table align="center"><tr><td>'
        f"<b>{title}</b><pre>\n{body}\n</pre>{note}"
        "</td></tr></table>"
    )


def calendar() -> list[list[int]]:
    """The contribution grid, as weeks of seven daily counts."""
    query = """
    query($login: String!) {
      user(login: $login) {
        contributionsCollection {
          contributionCalendar {
            weeks { contributionDays { contributionCount } }
          }
        }
      }
    }
    """
    out = run(
        ["gh", "api", "graphql", "-f", f"query={query}", "-F", f"login={USER}"],
        "contribution calendar query",
    )
    weeks = json.loads(out)["data"]["user"]["contributionsCollection"][
        "contributionCalendar"
    ]["weeks"]
    return [[day["contributionCount"] for day in week["contributionDays"]] for week in weeks]


def pop_svg(weeks: list[list[int]]) -> str:
    """The contribution year as a field, with a cannon shelling it.

    A gun turret stands in the middle of the grid, swings to each contribution
    day in turn and fires; the shell flies out and the square bursts when it
    lands. Days with no commits are never hit and never move — the cannon is
    the only thing that makes anything happen, which is the point.

    Everything is CSS keyframes and per-element animation-delay. GitHub serves
    this through an <img>, where scripts never run but stylesheets inside the
    SVG do, so each shell needs its own @keyframes: the flight path is a
    different vector every time.
    """
    cell, gap = 11, 3
    pitch = cell + gap
    columns = len(weeks)
    width = columns * pitch + gap
    height = 7 * pitch + gap

    # Light and dark are both painted here: an <img> gets no page CSS, so the
    # only way to answer the reader's theme is prefers-color-scheme inside.
    levels_light = ["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"]
    levels_dark = ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"]

    squares = [
        (x, y, count) for x, week in enumerate(weeks) for y, count in enumerate(week)
    ]
    targets = [(x, y, count) for x, y, count in squares if count]
    peak = max((count for _, _, count in targets), default=1)

    def level(count: int) -> int:
        if count == 0:
            return 0
        return min(4, 1 + int(count / peak * 3.999))

    def centre(x: int, y: int) -> tuple[float, float]:
        return gap + x * pitch + cell / 2, gap + y * pitch + cell / 2

    # The turret sits on the grid, not beside it, and small — roughly two cells
    # across, so it reads as a piece on the board rather than a mascot next to
    # it. Mid-field so there are targets to either side of it.
    gun_x, gun_y = width / 2, height / 2
    barrel = 17.0

    # A shot every 0.7s, however many days there are to shell.
    shots = len(targets)
    cycle = max(12.0, shots * 0.7)
    # 0.26s to cross up to 370px was a blur. 0.5 lets the eye follow the shell
    # out to where it lands, and still fits inside the 0.7s between shots.
    flight = 0.5
    pop_at = 0.968

    # Fire in a scattered order rather than left to right, so the turret swings
    # about the whole field instead of tracking steadily across it. md5 keeps
    # it identical on every rebuild — random.shuffle or hash() would rewrite
    # pop.svg daily and commit a diff on days nothing happened, and hash() is
    # salted per process besides.
    order = sorted(targets, key=lambda t: hashlib.md5(f"{t[0]},{t[1]}".encode()).digest())

    rules = [
        ".c{stroke-width:0;rx:2;transform-box:fill-box;transform-origin:center}",
        # Only a square that gets hit moves, and it moves when the shell lands.
        "@keyframes popg{"
        "0%,95%{transform:scale(1);filter:none}"
        "96.8%{transform:scale(1.6);filter:brightness(1.7)}"
        "98.4%{transform:scale(.82);filter:none}"
        "100%{transform:scale(1)}"
        "}",
        ".gun{fill:#57606a}",
        ".shell{fill:#57606a}",
        "@media (prefers-reduced-motion:reduce){"
        ".c,.turret,.shell{animation:none!important}.shell{opacity:0}}",
    ]
    for shade, light in enumerate(levels_light):
        rules.append(f".l{shade}{{fill:{light}}}")
    rules.append("@media (prefers-color-scheme:dark){")
    for shade, dark in enumerate(levels_dark):
        rules.append(f".l{shade}{{fill:{dark}}}")
    rules.append(".gun,.shell{fill:#adbac7}")
    rules.append("}")

    # One firing slot per target, offset half a slot so no keyframe sits at 0%.
    slot = cycle / max(shots, 1)
    fire_at = {t: (i + 0.5) * slot for i, t in enumerate(order)}

    # The barrel holds each bearing through its own shot, then swings to the
    # next. Interpolating between the held angles is what makes it track.
    # How long before firing the barrel is already on the bearing. It has to
    # leave room for the shell still in the air from the previous shot: at
    # slot*0.35 with a 0.5s flight in a 0.7s slot, the next target's hold began
    # before the last one landed, the sorted keyframes interleaved two targets,
    # and the barrel jumped 297 degrees between neighbouring stops.
    settle = max(0.0, min(slot * 0.35, (slot - flight) * 0.8))

    aim_stops = []
    swung = 0.0
    for index, target in enumerate(order):
        tx, ty = centre(target[0], target[1])
        angle = math.degrees(math.atan2(ty - gun_y, tx - gun_x))
        # atan2 returns (-180, 180], so a target just below the axis and the
        # next one just above are 350 degrees apart on paper and the barrel
        # takes the long way round — a full spin to move a few degrees. Unwrap
        # the sequence instead: keep adding turns until each step is the short
        # one, and let the angle run past 180 as it accumulates.
        if index:
            angle += round((swung - angle) / 360) * 360
        swung = angle
        at = fire_at[target]
        aim_stops.append((max((at - settle) / cycle * 100, 0.0), angle))
        aim_stops.append(((at + flight) / cycle * 100, angle))
    rules.append(
        "@keyframes aim{"
        + "".join(
            f"{stop:.3f}%{{transform:rotate({angle:.2f}deg)}}"
            for stop, angle in sorted(aim_stops)
        )
        + "}"
    )
    rules.append(
        # left center is the breech, where the barrel meets the wheel. The
        # default centre is the middle of the barrel itself, so it pivoted
        # about its own waist and the muzzle swept back through the mount.
        ".turret{transform-box:fill-box;transform-origin:left center;"
        f"animation:aim {cycle:.2f}s linear infinite}}"
    )

    shells = []
    for index, target in enumerate(order):
        tx, ty = centre(target[0], target[1])
        at = fire_at[target]
        launch = at / cycle * 100
        land = (at + flight) / cycle * 100
        rules.append(
            f"@keyframes f{index}{{"
            f"0%,{max(launch - 0.01, 0):.3f}%{{transform:translate(0,0);opacity:0}}"
            f"{launch:.3f}%{{transform:translate(0,0);opacity:1}}"
            f"{land:.3f}%{{transform:translate({tx - gun_x:.1f}px,{ty - gun_y:.1f}px);opacity:1}}"
            f"{min(land + 0.01, 100):.3f}%,100%{{"
            f"transform:translate({tx - gun_x:.1f}px,{ty - gun_y:.1f}px);opacity:0}}"
            f"}}"
        )
        shells.append(
            f'<circle class="shell" cx="{gun_x:.1f}" cy="{gun_y:.1f}" r="3.2" '
            f'style="animation:f{index} {cycle:.2f}s linear infinite"/>'
        )

    parts = []
    for x, y, count in squares:
        style = ""
        if count:
            # Wind the delay back so the pop's peak lands with the shell —
            # and land in [-cycle, 0), never a positive delay. A positive one
            # means the square has not started yet, so for the whole first
            # cycle the shells arrived at squares that could not react: ten
            # dead seconds before anything moved. A negative delay starts the
            # animation already part-way through, so it is in step from t=0.
            impact = fire_at[(x, y, count)] + flight
            delay = (impact - pop_at * cycle) % cycle - cycle
            style = f' style="animation:popg {cycle:.2f}s {delay:.3f}s infinite"'
        parts.append(
            f'<rect class="c l{level(count)}" x="{gap + x * pitch}" '
            f'y="{gap + y * pitch}" width="{cell}" height="{cell}"{style}/>'
        )

    # The gun: a barrel that swings, on a fixed mount. The rotating group has
    # no transform attribute of its own — a CSS animation on transform beats
    # the SVG attribute, so anything static there would simply be discarded.
    gun = (
        f'<g transform="translate({gun_x:.1f},{gun_y:.1f})">'
        f'<g class="turret">'
        f'<rect class="gun" x="0" y="-3" width="{barrel}" height="6" rx="2"/>'
        f"</g>"
        f'<circle class="gun" cx="0" cy="0" r="6.5"/>'
        f'<rect class="gun" x="-7" y="5" width="14" height="3.2" rx="1.6"/>'
        f"</g>"
    )

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="A year of contributions as a field, with a cannon firing '
        f'on each of the {shots} days with commits in turn">'
        f"<style>{''.join(rules)}</style>{''.join(parts)}{''.join(shells)}{gun}</svg>\n"
    )


def splice(text: str, marker: str, body: str) -> str:
    pattern = re.compile(
        rf"(<!--START_SECTION:{marker}-->).*?(<!--END_SECTION:{marker}-->)", re.S
    )
    if not pattern.search(text):
        sys.exit(f"README.md has no {marker} markers to write into")
    return pattern.sub(lambda m: f"{m.group(1)}\n{body}\n{m.group(2)}", text)


def main() -> None:
    weeks = calendar()
    (ROOT / "pop.svg").write_text(pop_svg(weeks))

    readme = ROOT / "README.md"
    hours, private = commit_hours()
    readme.write_text(
        splice(readme.read_text(), "commit-times", commit_table(hours, private))
    )
    print("wrote pop.svg and the commit-times section")


if __name__ == "__main__":
    main()
