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
        "\n\n<sub>Counted across public repositories only — set a `GH_PAT` "
        "secret to include private commits.</sub>"
    )
    return f"**{title}**\n\n```text\n" + "\n".join(lines) + "\n```" + note


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


# The farmer, drawn once at the origin with his feet on y=0, so the only thing
# the animations move is the group around him. Kept at module scope because a
# 30px stick figure either reads as a person or does not, and that is far
# easier to judge on its own than inside 370 popping squares.
WALKER = (
    # Head, then a torso pitched forward — upright he reads as strolling.
    '<circle class="skin" cx="1.5" cy="-27" r="4.4"/>'
    '<path class="ink" d="M1,-22.5 C0,-18 -1,-14 -2,-10.5"/>'
    # Both arms reach down and forward to the handles.
    '<path class="ink" d="M0,-19 L9.5,-13.5"/>'
    '<path class="ink" d="M-0.5,-16 L9.5,-11"/>'
    # Legs swing from the hip; the back one is half a stride behind.
    '<path class="leg" d="M-2,-10.5 L-6,0"/>'
    '<path class="leg back" d="M-2,-10.5 L2.5,0"/>'
    # The plough: two handles running back to a beam, and a blade in the soil.
    '<path class="ink" d="M9.5,-13.5 L20,2"/>'
    '<path class="ink" d="M9.5,-11 L21,-0.5"/>'
    '<path class="ink" d="M13.5,-7.5 L15,-9.5"/>'
    '<path class="skin" d="M18.5,0 l6,1.5 -5.5,3.5 z"/>'
)


def pop_svg(weeks: list[list[int]]) -> str:
    """The contribution year as a field, with someone ploughing across it.

    A figure walks the width of the grid; each square pops as he reaches its
    column, so the pops have a cause rather than firing at random. Contribution
    days burst — bigger scale, a brightness flash, a squash on the way back —
    while empty ground just gets turned over.

    Everything is CSS keyframes and per-square animation-delay: GitHub serves
    this through an <img>, where scripts never run but stylesheets inside the
    SVG do. The delay for a square is whatever makes its pop land at the moment
    the walker's own animation has him standing over that column.
    """
    cell, gap = 11, 3
    pitch = cell + gap
    columns = len(weeks)
    lane = 36  # headroom above the grid: the figure is 31.4 tall, plus the bob
    width = columns * pitch + gap
    height = 7 * pitch + gap + lane

    # Light and dark are both painted here: an <img> gets no page CSS, so the
    # only way to answer the reader's theme is prefers-color-scheme inside.
    levels_light = ["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"]
    levels_dark = ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"]

    squares = [
        (x, y, count) for x, week in enumerate(weeks) for y, count in enumerate(week)
    ]
    peak = max((count for _, _, count in squares if count), default=1)

    def level(count: int) -> int:
        if count == 0:
            return 0
        return min(4, 1 + int(count / peak * 3.999))

    # One crossing per cycle, at a walking pace rather than a sweep. He starts
    # and ends off-canvas so he enters and leaves rather than materialising.
    cycle = 12.0
    margin = 26
    span = width + 2 * margin
    # Align the PEAK of the pop, at 96.8%, rather than its first frame at 95%.
    # Aligning the start left every square swelling a beat after he had gone
    # by: the pop lasts 5% of the cycle, which is two and a half columns of
    # walking, so the disturbance visibly trailed him.
    pop_at = 0.968
    # And it is the blade that turns the soil, not the walker's feet — it is
    # drawn out to his right, so the column under it is ahead of his centre.
    blade = 19

    def arrival(x: int) -> float:
        """When the plough blade is over column x.

        This inverts the *walk* keyframes, not the grid: he covers
        width + 2*margin, so pacing him by column alone left him running two
        columns ahead of the squares he was supposed to be popping.
        """
        centre = gap + x * pitch + cell / 2
        return (centre - blade + margin) / span * cycle

    def delay(x: int) -> float:
        return (arrival(x) - pop_at * cycle) % cycle

    rules = [
        ".c{stroke-width:0;rx:2;transform-box:fill-box;transform-origin:center}",
        # Ground that is merely walked over gets turned, not popped.
        "@keyframes till{"
        "0%,95%{transform:scale(1)}"
        "97.2%{transform:scale(.82) rotate(8deg)}"
        "100%{transform:scale(1)}"
        "}",
        # A contribution day bursts: the overshoot and the squash under itself
        # are what make it read as a pop rather than a pulse.
        "@keyframes popg{"
        "0%,95%{transform:scale(1);filter:none}"
        "96.8%{transform:scale(1.95);filter:brightness(1.6)}"
        "98.4%{transform:scale(.82);filter:none}"
        "100%{transform:scale(1)}"
        "}",
        f"@keyframes walk{{"
        f"0%{{transform:translateX({-margin}px)}}"
        f"100%{{transform:translateX({width + margin}px)}}"
        f"}}",
        # A separate bob on an inner group, on its own short loop, so the gait
        # does not have to divide into the crossing time.
        "@keyframes bob{0%,100%{transform:translateY(0)}50%{transform:translateY(-2.5px)}}",
        "@keyframes stride{0%,100%{transform:rotate(-16deg)}50%{transform:rotate(16deg)}}",
        ".walker{animation:walk %.1fs linear infinite}" % cycle,
        ".bob{animation:bob .5s ease-in-out infinite}",
        # The legs carry their own stroke rather than borrowing .ink: they swing
        # from the hip, so they need transform-origin of their own anyway.
        ".ink,.leg{stroke:#57606a;fill:none;stroke-width:2.2;"
        "stroke-linecap:round;stroke-linejoin:round}",
        ".leg{transform-box:fill-box;transform-origin:top center;"
        "animation:stride .5s ease-in-out infinite}",
        ".leg.back{animation-delay:-.25s}",
        ".skin{fill:#57606a}",
        # A reader who asked their system not to animate gets the finished
        # field and a walker standing still in it, not a half-popped frame.
        "@media (prefers-reduced-motion:reduce){"
        ".c,.walker,.bob,.leg{animation:none!important}}",
    ]
    for shade, light in enumerate(levels_light):
        rules.append(f".l{shade}{{fill:{light}}}")
    rules.append("@media (prefers-color-scheme:dark){")
    for shade, dark in enumerate(levels_dark):
        rules.append(f".l{shade}{{fill:{dark}}}")
    rules.append(".ink,.leg{stroke:#adbac7}.skin{fill:#adbac7}")
    rules.append("}")

    parts = []
    for x, y, count in squares:
        name = "popg" if count else "till"
        parts.append(
            f'<rect class="c l{level(count)}" x="{gap + x * pitch}" '
            f'y="{lane + gap + y * pitch}" width="{cell}" height="{cell}" '
            f'style="animation:{name} {cycle:.1f}s {delay(x):.3f}s infinite"/>'
        )

    # Three nested groups, and the middle one has to exist: a CSS animation on
    # transform overrides the SVG transform attribute on the same element, so
    # putting the vertical placement on .bob had the bob animation discard it
    # and draw him above the canvas, clipped out of the picture entirely.
    walker = (
        '<g class="walker">'
        f'<g transform="translate(0,{lane})">'
        f'<g class="bob">{WALKER}</g>'
        "</g></g>"
    )

    green = sum(1 for _, _, count in squares if count)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="A year of contributions as a field, {green} of them days '
        f'with commits, popping as someone ploughs across it">'
        f"<style>{''.join(rules)}</style>{''.join(parts)}{walker}</svg>\n"
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
