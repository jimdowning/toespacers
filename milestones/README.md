# Milestones

Everything `generate.py` and `tools/*.py` produce goes to `../outputs/` by
default, which is gitignored - cheap to regenerate, not worth a commit every
time you tweak a config. When a build (or a verification render, or a
comparison plot) is worth keeping permanently - a real print you're happy
with, a reference for a design decision, a "this is what broke" snapshot -
copy it in here and commit it, with a name that says what it is and why:

```bash
cp ../outputs/output_left.stl   2025-09-04_first-eccentric-fit_left.stl
cp ../outputs/output_right.stl  2025-09-04_first-eccentric-fit_right.stl
git add 2025-09-04_first-eccentric-fit_*.stl
git commit -m "Milestone: first eccentric-waist fit, both feet"
```

Include the `configs/*.json` that produced it in the same commit if it's
not already committed as-is, so the milestone and the config that generated
it stay in sync.
