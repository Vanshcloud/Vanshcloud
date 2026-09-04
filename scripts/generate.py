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


def pop_svg(weeks: list[list[int]]) -> str:
    """The contribution grid as bubble wrap: every square pops in turn.

    Every square, not only the green ones — an empty square that stays rigid
    while the wave crosses it breaks the illusion that the whole sheet is
    being popped. Contribution days pop harder, and overshoot on the way back,
    so the wave still reads as tracking the year's activity.

    CSS animation rather than SMIL or script, because GitHub serves this
    through an <img> — scripts never run there, stylesheets inside the SVG do.
    """
    cell, gap = 11, 3
    pitch = cell + gap
    width = len(weeks) * pitch + gap
    height = 7 * pitch + gap

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

    # The delay is what makes the wave. Sweeping ~370 squares needs a far
    # tighter stagger than sweeping the 20 green ones did: five seconds for the
    # crossing, and a pop lasting 5% of the cycle, puts roughly two dozen
    # squares mid-bounce at once — a band about four columns wide, which reads
    # as a wave rather than as the whole grid twitching in unison.
    sweep = 5.0
    step = sweep / max(len(squares), 1)
    cycle = sweep + 2.0

    rules = [
        ".c{stroke-width:0;rx:2;transform-box:fill-box;transform-origin:center}",
        # The bounce sits at the END of each square's cycle, not the start: a
        # square is at rest for 95% of it, and the animation-delay decides when
        # its turn comes round.
        "@keyframes pop{"
        "0%,95%{transform:scale(1)}"
        "97.2%{transform:scale(1.28)}"
        "100%{transform:scale(1)}"
        "}",
        # A contribution day goes bigger, flashes, and squashes under itself
        # before settling — the overshoot is what makes it read as a pop
        # rather than a pulse.
        "@keyframes popg{"
        "0%,95%{transform:scale(1);filter:none}"
        "96.8%{transform:scale(1.95);filter:brightness(1.6)}"
        "98.4%{transform:scale(.82);filter:none}"
        "100%{transform:scale(1)}"
        "}",
        # A reader who asked their system not to animate gets the finished
        # grid instead of a still frame of a half-popped one.
        "@media (prefers-reduced-motion:reduce){.c{animation:none!important}}",
    ]
    for shade, light in enumerate(levels_light):
        rules.append(f".l{shade}{{fill:{light}}}")
    rules.append("@media (prefers-color-scheme:dark){")
    for shade, dark in enumerate(levels_dark):
        rules.append(f".l{shade}{{fill:{dark}}}")
    rules.append("}")

    parts = []
    # Chronological order, so the wave crosses left to right like the year.
    for order, (x, y, count) in enumerate(squares):
        name = "popg" if count else "pop"
        parts.append(
            f'<rect class="c l{level(count)}" x="{gap + x * pitch}" y="{gap + y * pitch}" '
            f'width="{cell}" height="{cell}" '
            f'style="animation:{name} {cycle:.3f}s {order * step:.3f}s infinite"/>'
        )

    green = sum(1 for _, _, count in squares if count)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="A year of contributions, {green} of them days with commits, '
        f'popping one square at a time">'
        f"<style>{''.join(rules)}</style>{''.join(parts)}</svg>\n"
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
