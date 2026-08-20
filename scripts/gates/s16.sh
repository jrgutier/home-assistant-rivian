#!/usr/bin/env bash
# S16 — the claim register and the prose must agree.
#
# WHY THIS GATE EXISTS. WS_CONTENTION.md carries a claim register: each claim gets
# a verdict, and rows list the downstream files that cite it. Nothing checked that
# the downstream edits were ever made. Every other invariant here is pinned --
# f9 pins the ceiling constants, s15 pins the retired opt-out flag's absence, s06c
# pins subscription-failure typing -- register consistency was the one that was not.
#
# (That flag is named here by description, not spelled out: s15 greps scripts/ for
# the literal token, so writing it in this comment fails s15 -- the same trap
# s15.sh:161 records having already sprung once.)
#
# The result, found 2026-08-20: the document asserted FIVE things its own register
# refutes (C1s, C1c, C2, C4, C8 -- plus C6/C7 presented as measured when their arms
# were dropped), and scripts/gates/f8.sh ENFORCED one of them. The register even
# said "Both need rewording in the same commit that changes the protocol, never
# before" -- a deferral that, with no tripwire, became never.
#
# WHAT THIS CAN AND CANNOT DO. It pins KNOWN-retired phrases. A newly falsified
# claim still needs its phrase added here. That is the same tradeoff f9 and s15
# already make, and it is strictly better than no check at all.
source "$(dirname "$0")/_lib.sh"
echo "S16 — claim register vs prose"

DOC="$HA/docs/development/WS_CONTENTION.md"
RVM="$HA/docs/development/RVM_FIXTURES.md"
PRD="$HA/prd.json"
GATES="$HA/scripts/gates"
PY_BIN="$(resolve_python "$HA")"

have_path "the claim register exists" "$DOC"
have_path "the fixture record exists" "$RVM"
have_path "prd.json exists" "$PRD"

# --- 1. no gate ENFORCES a retired claim ------------------------------------
# The sharp end. f8.sh required the literal "sole subscriber" in the f8 record
# whenever the verdict contained INCONCLUSIVE -- and per the register's own note,
# `found` is a substring search over a document that under P1 keeps every retracted
# INCONCLUSIVE verdict forever, so that branch was PERMANENTLY taken. A gate
# demanding evidence for a protocol claim C8 falsified.
#
# A comment ABOUT the removal is fine and wanted; an executable requirement is not.
# So: look only at lines that are not comments.
# Counted, not short-circuited. The first version of this check used
# `[ ... ] && continue` inside the loop and then called ok() unconditionally after
# it, so it reported PASS even when the loop had found an offender -- a gate that
# could not fail is the exact defect this file exists to catch, and it shipped in
# this file first. Arm-proved both directions before it was trusted.
_offenders=0
for g in "$GATES"/*.sh; do
  case "$(basename "$g")" in s16.sh|_lib.sh) continue ;; esac
  # Strip comments first: a comment explaining the removal is wanted; an
  # executable line carrying the phrase is the thing being forbidden.
  if { grep -vE '^[[:space:]]*#' "$g" || true; } | grep -qF 'sole subscriber'; then
    bad "$(basename "$g") still ENFORCES 'sole subscriber' (claim C8 is FALSIFIED)"
    _offenders=$((_offenders + 1))
  fi
done
if [ "$_offenders" -eq 0 ]; then
  ok "no gate enforces the retired sole-subscriber protocol"
fi

# --- 2. retired phrases appear only under a label ---------------------------
# Each retired claim, and the marker that must accompany every surviving mention.
# Checked per-line: a bare assertion is a line carrying the phrase with no label
# on it and no strikethrough.
check_labelled() {
  local desc="$1" phrase="$2" file="$3" bare
  if [ ! -f "$file" ]; then bad "$desc  (missing: $file)"; return; fi
  # Windowed, not line-local. Two wrong versions preceded this one:
  #
  #   * exempting EVERY `>` line unconditionally -- which masks a bare assertion
  #     written as a blockquote, the natural markdown form for a "note", so a
  #     re-asserted falsified claim would pass silently;
  #   * requiring the label ON the line -- which flags the legitimate case where a
  #     superseded account is quoted verbatim and labelled by the prose around it
  #     ("The replacement account was:" / "That account is also wrong.").
  #
  # A mention is labelled if a label appears within 3 lines either side of it.
  # python3, not grep: gates already shell out to it (see f8.sh) and a windowed
  # test is not expressible in a line-based pipeline.
  bare=$(PHRASE="$phrase" "$PY_BIN" - "$file" <<'EOF'
import io, os, re, sys
phrase = os.environ["PHRASE"]
labels = re.compile(r"FALSIFIED|SUPERSEDED|RETRACT|UNVERIFIED|used to read|attributed"
                    r"|~~|NOT measured|superseded account|replacement account|also wrong")
lines = io.open(sys.argv[1], encoding="utf-8").read().split("\n")
bare = 0
for i, line in enumerate(lines):
    if phrase not in line:
        continue
    window = "\n".join(lines[max(0, i - 3): i + 4])
    if not labels.search(window):
        bare += 1
print(bare)
EOF
)
  if [ "$bare" -eq 0 ]; then ok "$desc"
  else bad "$desc  ($bare unlabelled)"; fi
}

check_labelled "C1s: 'one active subscription per user session' is labelled in the register" \
               "one active subscription per user session" "$DOC"
check_labelled "C1s: labelled in prd.json" \
               "one active subscription per user session" "$PRD"
check_labelled "C1s: labelled in the fixture record" \
               "one active subscription per user session" "$RVM"
check_labelled "C8: 'must run as sole subscriber' is labelled in the register" \
               "must run as sole subscriber" "$DOC"

# --- 3. the register still carries the verdicts these checks rest on --------
# If a verdict is deleted, the checks above go quiet for the wrong reason.
contains "C1s is still recorded FALSIFIED"     'FALSIFIED — STATIC' "$DOC"
# Pin the VERDICT, not just the row label. Pinning '**C8**' alone meant the row
# could be flipped to VERIFIED and s16 would still print
# "PASS  C8 is still recorded FALSIFIED" -- which is precisely the
# "register said VERIFIED where the arms FALSIFIED" failure (commit 121b71e),
# and this gate is the only thing guarding it.
contains "C8 is still recorded FALSIFIED" \
         '| **C8** | `:74-76`' "$DOC"
contains "C8's verdict is still FALSIFIED, not flipped" \
         'sole subscriber. `s08a` cannot be done from a dev machine while Home Assistant is running."* | **FALSIFIED.**' "$DOC"
contains "C6 is still recorded UNVERIFIED" \
         '| **C6** | `:55-60` close codes' "$DOC"
contains "C6's verdict is still UNVERIFIED, not flipped" \
         'their meanings | **UNVERIFIED — arms dropped by ruling 28.**' "$DOC"
contains "the instrument defect is cited"      '759123d'            "$DOC"

# --- 4. the title no longer asserts what the register refutes ---------------
if head -1 "$DOC" | grep -qF 'allows one connection per user session'; then
  bad "the document title still asserts claims C1s/C1c"
else
  ok "the title does not assert a falsified claim"
fi

summary S16
