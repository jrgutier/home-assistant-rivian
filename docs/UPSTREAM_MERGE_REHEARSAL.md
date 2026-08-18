# Tracking upstream after vendoring

We merge from `bretterer` periodically and never push back. Vendoring the client
changed how that works, and this file records the process plus a rehearsal of it,
so the mechanics are known to work before they are needed rather than being worked
out during an urgent fix.

There are now **two** upstream flows, not one, and only the first is a git merge.

---

## 1. The integration — `upstream/main`, an ordinary merge

```bash
git remote get-url upstream   # https://github.com/bretterer/home-assistant-rivian.git
git fetch upstream
git log --oneline HEAD..upstream/main        # what is waiting
git merge --no-commit --no-ff upstream/main  # rehearse
git merge --abort                            # then decide
```

### Rehearsal, run against the current tree

`git merge --no-commit --no-ff upstream/main` reports **"Already up to date"**.
`HEAD..upstream/main` is empty and the merge base *is* `upstream/main`'s head
(`a7e29e9`), because s05 merged `1.5.3b5` and upstream has not moved since.

That is a real result but a weak rehearsal: a no-op merge exercises nothing. So
the merge was replayed from the tag s05 left behind, in a throwaway worktree:

```bash
git worktree add --detach /tmp/rehearsal pre-merge-1.5.3b5
cd /tmp/rehearsal
git merge --no-commit --no-ff 1.5.3b5   # exit 1
git diff --name-only --diff-filter=U    # 18 files
git merge --abort                       # clean
```

**18 files conflicted.** Recording the actual list matters more than the count,
because it is the same list next time:

| File | Why it conflicts |
|---|---|
| `custom_components/rivian/coordinator.py` | the big one — both sides restructure it |
| `custom_components/rivian/const.py` | entity tables, both sides add |
| `custom_components/rivian/sensor.py`, `switch.py`, `number.py`, `cover.py`, `lock.py`, `climate.py`, `button.py`, `update.py` | our entity renaming and i18n conversion vs upstream's additions |
| `custom_components/rivian/strings.json`, `translations/en.json` | modify/delete — we deleted `strings.json`, upstream still has it |
| `custom_components/rivian/manifest.json` | version and requirements |
| `requirements.txt`, `pyproject.toml`, `.pre-commit-config.yaml`, `.devcontainer/setup`, `CLAUDE.md` | tooling, both sides |

The worktree was removed and the working tree is unchanged: this is a dry run.

### The one that bites without failing

Upstream fixes of the shape `INITIAL_UPDATE_TIMEOUT = 60`, the `vehicleMileage`
oscillation guard, the `gnssLocation` resilience — small, behavioural, in a file
whose conflicts are large — are dropped by a take-ours resolution **without any
test failing**, and surface weeks later as a field bug. `scripts/gates/s05.sh`
asserts those by value rather than by symbol for exactly that reason. Extend it
whenever a merge brings in a fix of that shape.

Never resolve with `-X ours` or `-X theirs` wholesale. The gates cannot see the
difference on most files.

---

## 2. The client — no merge, because it is vendored

`custom_components/rivian/rivian_client/` is the client, edited in place. There is
no package to bump, no publish step, and no `requirements` entry pointing at it —
that moving git URL is what made installs unreproducible and is the thing
vendoring removed.

It also removed the path upstream client fixes used to arrive by.
`scripts/sync_upstream_client.sh` is that path:

```bash
scripts/sync_upstream_client.sh                    # what is waiting upstream
scripts/sync_upstream_client.sh --check <a>..<b>   # dry run
scripts/sync_upstream_client.sh <a>..<b>           # apply
```

It fetches `bretterer/rivian-python-client` as the `client-upstream` remote
**directly into this repo**. It deliberately does not use the sibling
`rivian-python-client` checkout: that repo is a staging area at best and is slated
for archival, and a process that only works on one laptop is not a process. Git is
happy to carry the unrelated history alongside ours.

Path mapping: upstream is `src/rivian/<f>`, we are
`custom_components/rivian/rivian_client/<f>`, so `-p3 --directory=…`. `-p2` leaves
an extra `rivian/` segment and fails with "No such file or directory" — the first
thing to check if this ever stops working.

### Rehearsal

Upstream's newest commit touching `src/rivian` (`fb7d7a5`, "Fix cabin climate
temperature mapping") was fed through the script. It reported:

> this range is ALREADY in the vendored tree (it reverse-applies cleanly)

which is the useful result, and validates the whole mechanism end to end: the
patch **reverse**-applies against `rivian_client/`, so the commit is present *and*
the path mapping is right. Forward-applying the same patch fails with "patch does
not apply", confirming the two states are distinguishable — they need opposite
responses and both fail a naive forward `--check`.

### After any sync

1. Update the vendored-from marker in `rivian_client/__init__.py`. It is the only
   record of which upstream commit the copy corresponds to; git cannot tell you.
2. `.venv/bin/pytest -q && .venv/bin/python scripts/check_coverage.py`
3. `bash scripts/load_test.sh` — upstream may import something Home Assistant core
   does not ship, which the suite cannot catch.
4. Do **not** run `ruff --fix` across `rivian_client/`. It is excluded in
   `pyproject.toml` on purpose: reformatting vendored code recreates the permanent
   divergence vendoring exists to remove.

### Invariant worth keeping

While `rivian-python-client` still exists, its `src/rivian/` and our
`rivian_client/` are byte-identical except `__init__.py`, which carries the
`vendored+<sha>` marker instead of importing the Hatchling-generated
`__version__.py`. `scripts/gates/s14.sh` asserts this while the sibling repo is
present, and skips when it is not, so archiving the repo does not fail the gate.
