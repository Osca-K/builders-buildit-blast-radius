# Coverage-guided Blast Radius

Build-time line and resource coverage is derived exclusively from the pristine pinned
sqlglot commit. Runtime maps changed old-source lines to pytest node IDs and translates
them to the supplied test numbers. Shared fixtures have shared contexts. Initialization,
resource, syntax-error, and unknown changes use conservative fallbacks. Python AST
comparison removes syntactically equivalent edits; SQL/data fixtures are never treated
as Python comments. Every selected set is scheduled with one through eight workers,
choosing the lowest integer-millisecond makespan plus worker overhead.

No patch-to-answer or edit-to-answer tables are used. Public sample answers are used
only by the external validation scorer, never copied into the image or read by selector.

Build: `docker build -t blast-radius .`

The committed index is derived solely from the pristine pinned source at
eb11aec4be8cb2122afe713a4816662c3f0fb2fa. Reproduce it with
`docker build -f Dockerfile.training -t blast-radius-training .`.
The training run passed 1,620 tests and 25,440 subtests, with one expected skip.
Receiver contexts record inherited dialect flags as well as executed lines.
Changed statements select observed line users and enclosing expression headers;
uncovered statements fall back to the enclosing function. Replacement additions
map to the removed lines; pure insertions include both adjacent old lines.
Mixed class/method edits retain file users. Literal class-value-only edits can use
attribute readers, expanded to inherited declaration modules from pristine classes.

The current index also records operand-type observations from the unmodified test
suite. When a patch only changes `is`/`is not` to `==`/`!=`, tests are removed
only where every observation at that exact source location proves the comparison
equivalent. Missing, custom, or conflicting types retain the test.

Public sample validation: 117.638 simulated seconds, zero missed commits,
versus 122.525 for submitted commit dafc288. Twenty-four dependency tracing and selector regression tests cover
replacement/insertion boundaries, mixed edits, missing maps and inherited flags.
Literal negative numbers and containers use attribute readers; calls and invalid
literal containers retain file users.
Sample answers remain outside the runtime image. Hidden-set performance is
measured separately by the competition scorer.

A supplementary pristine run observes expression `arg_types` declarations and
derived `required_args` reads, including inherited declarations. It passed all
1,620 tests and 25,440 subtests (one expected skip) and keeps the existing pristine
line, resource and operand-type coverage unchanged. Only string-to-boolean schema
dictionaries in expression modules can use this map; mixed edits and invalid
schema shapes retain the conservative import dependency fallback. Reproduce the
supplementary collection with `docker build -f Dockerfile.schemas .`.
Experimental dictionary key tracing is disabled in this release pending further
checks for consumers implemented in C.

Run: `docker run --rm --network none --read-only --user nobody -v DATA:/data:ro blast-radius`

If the generated index is absent or catalog-incompatible, runtime selects all tests.
The reproduction build fails if coverage collection cannot complete.
