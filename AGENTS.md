# AGENTS.md

Instructions for AI agents modifying this repository.

## Golden rule

**Commit after every change.** No change is "done" until it is committed.

1. Make one logical change (one feature, one fix, one tweak to a parameter).
2. Run the generator to confirm it still renders:
   ```bash
   python3 src/psybeat.py
   ```
3. Stage and commit immediately:
   ```bash
   git add -A
   git commit -m "<area>: <imperative summary>"
   ```
4. Do **not** batch unrelated changes into one commit.
5. Do **not** leave the working tree dirty at the end of a session. Either
   commit or `git checkout -- .` the experiment.

Commit message style: conventional-ish, lowercase, imperative.
Examples:
- `bass: shorten 16th envelope for tighter roll`
- `drums: add open hat on the 16th before backbeat`
- `cli: add --seed flag`
- `docs: document sidechain chain`

## Project facts

- Environment: headless Linux sandbox, root user, internet available.
- Pure-DSP: audio is generated numerically. No external samples unless a
  change explicitly adds them (and then note licensing in the commit).
- Determinism: a fixed RNG seed is used for noise. If you add
  randomness, expose it as a seed and keep the default reproducible.
- Output files (`out/`, `*.wav`, `*.mp3`) are gitignored — never commit them.

## Testing

There is no test suite yet. Minimum check before committing is that
`python3 src/psybeat.py` exits 0 and prints the rendered duration/peak.
If you add a test suite, wire it into `tools/check.sh` and mention it here.
