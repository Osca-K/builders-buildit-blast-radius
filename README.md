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
Changed functions select all observed callers of the smallest enclosing function;
module and class edits select the recorded file users.

Public sample validation: 190.943 simulated seconds, zero missed commits.
Sample answers remain outside the runtime image. Hidden-set performance is
measured separately by the competition scorer.

Run: `docker run --rm --network none --read-only --user nobody -v DATA:/data:ro blast-radius`

If the generated index is absent or catalog-incompatible, runtime selects all tests.
The reproduction build fails if coverage collection cannot complete.
