"""The decisions in generate.py that are worth a check, and no more.

Run with `python scripts/selftest.py`. No framework, no network: everything
here is pure formatting over a Counter and a grid.
"""

import math
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from generate import commit_table, pop_svg  # noqa: E402

# A run that could not see private repositories has to say so. Publishing the
# smaller number bare is the failure this whole flag exists to prevent.
morning_heavy = Counter({9: 3, 2: 1})
assert "GH_PAT" not in commit_table(morning_heavy, True)
assert "GH_PAT" in commit_table(morning_heavy, False)

# Rendered as a <pre> in a table, never a fence: a fence spans the full page
# width and carries a copy button, and neither belongs on a profile.
table = commit_table(morning_heavy, True)
assert "```" not in table, "a fence would take the whole page width"
assert table.startswith('<table align="center">') and "<pre>" in table
assert "\n\n" not in table, "a blank line drops GitHub back into markdown mid-block"

# The headline follows the commits rather than being decoration.
assert "early" in commit_table(morning_heavy, True)
assert "Night" in commit_table(Counter({23: 5}), True)

# Only days with commits are shelled, and only they move. A grid where the
# empty squares twitch has something firing at nothing.
grid = [[0] * 7, [3, 0, 0, 0, 0, 0, 1]]
svg = pop_svg(grid)
assert svg.count("<rect") >= 14, "every day needs a square"
assert svg.count("animation:popg") == 2, "the two contribution days burst"
assert svg.count("animation:f") == 2, "one shell per target"
assert 'class="turret"' in svg and svg.count('class="shell"') == 2

# The delays must be byte-identical run to run, or the daily workflow commits
# a churned pop.svg on days when nothing actually happened.
assert pop_svg(grid) == svg, "output must be stable"

# A square bursts when its shell lands, not on some unrelated beat. The shells
# are emitted in firing order and the rects in grid order, so they have to be
# matched by where the shell actually flies to — which is the useful check
# anyway: if the flight and the pop are ever wired to different numbers, the
# squares go off with nothing arriving.
CELL, GAP, PITCH, POP_AT = 11, 3, 14, 0.968
COLUMNS = 6
wide = [[1] * 7 for _ in range(COLUMNS)]
svg = pop_svg(wide)
cycle = float(re.search(r"animation:popg ([\d.]+)s", svg).group(1))
gun_x, gun_y = (COLUMNS * PITCH + GAP) / 2, (7 * PITCH + GAP) / 2

bursts = {}
for x_at, y_at, delay in re.findall(
    r'<rect class="c l\d+" x="([\d.]+)" y="([\d.]+)"[^>]*?animation:popg [\d.]+s (-?[\d.]+)s', svg
):
    bursts[(float(x_at), float(y_at))] = float(delay)
assert len(bursts) == COLUMNS * 7, "every contribution day needs a shell"
# Every delay must be negative. A positive one leaves the square dormant until
# it elapses, so the opening cycle plays with shells landing on dead squares.
assert all(d < 0 for d in bursts.values()), "a positive delay means a dead first cycle"

for flight_css in re.findall(r"@keyframes f\d+\{.*?\}(?=@|$)", svg, re.S):
    dx, dy, land = re.search(
        r"([-\d.]+)px,([-\d.]+)px\);opacity:1\}([\d.]+)%", flight_css
    ).groups()
    # Where the shell is aimed, turned back into the square it should hit.
    col = round((gun_x + float(dx) - GAP - CELL / 2) / PITCH)
    row = round((gun_y + float(dy) - GAP - CELL / 2) / PITCH)
    key = (float(GAP + col * PITCH), float(GAP + row * PITCH))
    assert key in bursts, f"shell aimed at ({col},{row}), which is not a target"
    impact = float(land) / 100 * cycle
    fires_at = (bursts[key] + POP_AT * cycle) % cycle
    apart = min((fires_at - impact) % cycle, (impact - fires_at) % cycle)
    assert apart < 1e-2, f"square ({col},{row}) bursts {apart:.3f}s from impact"

# The barrel pivots at the breech, not at its own waist. transform-origin
# defaults to the centre of the box, which for a barrel drawn from the mount
# outwards is halfway along it — the muzzle then sweeps back through the wheel.
assert "transform-origin:left center" in svg, "the barrel must pivot at the breech"

# Consecutive bearings must never be more than half a turn apart. atan2 returns
# (-180, 180], so a target just below the axis followed by one just above reads
# as 350 degrees of travel and the barrel takes the long way round — a full
# spin to move a few degrees.
aim = re.search(r"@keyframes aim\{(.*?)\}(?=@|\.)", svg, re.S).group(1)
bearings = [float(a) for a in re.findall(r"rotate\((-?[\d.]+)deg\)", aim)]
steps = [abs(b - a) for a, b in zip(bearings, bearings[1:])]
assert steps and max(steps) <= 180.0001, f"barrel swings {max(steps):.0f} degrees the long way"

# Each target holds one bearing across two stops, so the sequence must come in
# equal pairs. If a hold starts before the previous shell lands the sorted
# keyframes interleave two targets and the barrel jumps between them.
assert all(bearings[i] == bearings[i + 1] for i in range(0, len(bearings) - 1, 2)), \
    "aim stops interleaved: a hold began before the previous shot landed"

# The turret has to be free to rotate: a CSS animation on transform overrides
# the SVG transform attribute on the same element, so the mount's position must
# live on a separate group or the aim animation simply discards it.
assert re.search(r'<g transform="translate\([\d.]+,[\d.]+\)"><g class="turret">', svg), \
    "the turret needs its own group inside a positioned mount"

print("selftest ok")
