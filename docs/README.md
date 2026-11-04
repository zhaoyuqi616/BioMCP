# BioMCP documentation

Start with the guide matching your task. Runtime behavior is documented separately from proposed production work.

| Task | Read |
|---|---|
| Use the single-gene dashboard | [v0.6 guide](guides/v0.6.md) |
| Install and run | [Project quick start](../README.md#quick-start) |
| Test the MVP end to end | [Validation tutorial](guides/validation.md) |
| Configure providers, limits and local login | [Configuration](guides/configuration.md) |
| Understand the code and boundaries | [Current architecture](architecture/overview.md) |
| Review the next implementation stages | [MVP design proposal](architecture/mvp-design.md) |
| Check what is actually delivered | [Implementation status](operations/implementation-status.md) |
| Evaluate deployment readiness | [Production review and release gates](operations/production-readiness.md) |
| Understand architecture decisions | [Decision records](architecture/decisions/README.md) |
| Consult previous versions | [Historical documentation](history/README.md) |

## Documentation conventions

- `guides/`: executable user/developer procedures for the current release.
- `architecture/overview.md`: implemented components and dependency flow.
- `architecture/mvp-design.md`: target design, including work not yet delivered.
- `architecture/decisions/`: dated decisions with status and consequences.
- `operations/`: implementation evidence, limitations and deployment gates.
- `history/`: archived guidance; current setup instructions take precedence.

Run `python scripts/check.py` to validate code, tests and local documentation links. Run commands from the repository root unless stated otherwise. A clean layout and passing local checks do not establish production readiness; hosted access controls and other open gates remain in the implementation status.
