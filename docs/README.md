# Docs

The design level of kumi. Start here to understand how the team is built, then follow into the specifics.

- [ARCHITECTURE.md](ARCHITECTURE.md): the design principle (a plugin system: one contract, a dispatcher that knows nothing specific, one shared format), the four pillars, the invariants, and the role shapes. Read this to understand *why* the team is uniform and how it stays that way as it grows.
- [DIAGRAMS.md](DIAGRAMS.md): every diagram, drawn in Mermaid so GitHub renders it with no build step. Six levels, from the system fan-out down to a single run.
- [MANAGING-SPECIALISTS.md](MANAGING-SPECIALISTS.md): the operations guide for adding, disabling, modifying, removing, or renaming a specialist, or adding a whole new stack.
- [MEMORY.md](MEMORY.md): how kumi remembers finished work between sessions. One hook captures state when an agent stops, another restores it when a new session starts.
- [OBSERVABILITY.md](OBSERVABILITY.md): the activity log and the per-session and per-agent token and time metrics.
- [ANATOMY.md](ANATOMY.md): what makes up one specialist and the whole package, file by file.
- [CAST.md](CAST.md): who the specialists are, and where their names come from.
- [WALKTHROUGH-ADD-PHP-AGENT.md](WALKTHROUGH-ADD-PHP-AGENT.md): a full worked example of adding a new specialist.

For the roster of specialists, see [../skills/README.md](../skills/README.md). For how to add one, see [../CONTRIBUTING.md](../CONTRIBUTING.md).
