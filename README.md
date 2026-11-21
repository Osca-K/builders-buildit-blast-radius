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

Run: `docker run --rm --network none --read-only --user nobody -v DATA:/data:ro blast-radius`

If the generated index is absent or catalog-incompatible, runtime selects all tests.
The build intentionally fails if coverage collection cannot complete.
