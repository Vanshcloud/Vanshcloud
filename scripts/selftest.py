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

# Every day animates, but a contribution day gets the louder keyframes: an
# empty square sitting rigid while the wave crosses it breaks the illusion.
svg = pop_svg([[0] * 7, [3, 0, 0, 0, 0, 0, 1]])
assert svg.count("<rect") == 14, "every day needs a square"
# The 15th is animation:none in the reduced-motion rule, not a square.
assert svg.count("animation:") - svg.count("animation:none") == 14, "every square animates"
assert svg.count("animation:popg") == 2, "the two contribution days pop harder"
assert svg.count("animation:pop ") == 12, "the rest get the quiet bounce"
assert "prefers-reduced-motion" in svg and "prefers-color-scheme" in svg

# The delays must be byte-identical run to run, or the daily workflow commits
# a churned pop.svg on days when nothing actually happened.
assert pop_svg([[0] * 7, [3, 0, 0, 0, 0, 0, 1]]) == svg, "output must be stable"

# ...and scattered rather than marching in position order, which is the whole
# point of hashing the coordinates.
grid = [[1] * 7 for _ in range(12)]
delays = [float(d) for d in re.findall(r"animation:\w+ [\d.]+s ([\d.]+)s", pop_svg(grid))]
assert delays != sorted(delays), "delays must not follow position order"

print("selftest ok")
