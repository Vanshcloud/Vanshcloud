"""The two decisions in generate.py that are worth a check, and no more.

Run with `python scripts/selftest.py`. No framework, no network: everything
here is pure formatting over a Counter and a grid.
"""

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

# The headline follows the commits rather than being decoration.
assert "early" in commit_table(morning_heavy, True)
assert "Night" in commit_table(Counter({23: 5}), True)

# Every day animates, but a contribution day bursts while bare ground is only
# turned over — an empty square holding rigid as the walker passes gives it away.
svg = pop_svg([[0] * 7, [3, 0, 0, 0, 0, 0, 1]])
assert svg.count("<rect") == 14, "every day needs a square"
# Counted by name, since the walker's own keyframes live in the stylesheet too.
assert svg.count("animation:popg") == 2, "the two contribution days pop"
assert svg.count("animation:till") == 12, "the rest are only turned over"
assert svg.count("animation:popg") + svg.count("animation:till") == 14, "no square left out"
assert "prefers-reduced-motion" in svg and "prefers-color-scheme" in svg
assert 'class="walker"' in svg, "someone has to be doing the ploughing"
# The vertical placement must sit on a group that no CSS animation touches: a
# CSS transform beats the SVG attribute, so an animated element cannot also
# carry its own position — he ends up drawn above the canvas and clipped away.
assert re.search(r'class="walker"><g transform="translate\(0,\d+\)"><g class="bob"', svg), \
    "the walker needs a static group between walk and bob"

# The delays must be byte-identical run to run, or the daily workflow commits
# a churned pop.svg on days when nothing actually happened.
assert pop_svg([[0] * 7, [3, 0, 0, 0, 0, 0, 1]]) == svg, "output must be stable"

# A square pops when the walker reaches its column. Every square in a column
# shares one moment, and that moment is where the walker actually is — checked
# against the same arithmetic the walk animation runs on, because if the two
# drift apart the squares pop with nobody standing over them.
CYCLE, POP_AT, NCOLS = 12.0, 0.968, 12
BLADE = 19
CELL, GAP, PITCH, MARGIN = 11, 3, 14, 26
WIDTH = NCOLS * PITCH + GAP
SPAN = WIDTH + 2 * MARGIN
grid = [[1] * 7 for _ in range(NCOLS)]
delays = [float(d) for d in re.findall(r"animation:\w+ [\d.]+s ([\d.]+)s", pop_svg(grid))]
columns = [delays[i * 7:(i + 1) * 7] for i in range(NCOLS)]
for x, column in enumerate(columns):
    assert len(set(column)) == 1, "one column, one moment"
    fires_at = (column[0] + POP_AT * CYCLE) % CYCLE
    # Where the walk keyframes actually put the blade, margins included —
    # pacing him by column alone once left him two columns ahead of his pops.
    walker_at = (GAP + x * PITCH + CELL / 2 - BLADE + MARGIN) / SPAN * CYCLE
    assert abs(fires_at - walker_at) < 1e-3, f"column {x} pops with nobody there"

print("selftest ok")
