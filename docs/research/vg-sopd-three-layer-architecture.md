# VG-SOPD Three-Layer Architecture

Status: research background

This note exists to preserve the intent of the older VG-SOPD design document
without treating it as part of the primary user-facing documentation set.

It describes a research-oriented training concept:

- verifier-grounded semi-on-policy distillation
- staged training and relabel flows above the execution core
- continued use of `ms-swift` as the training backend
- compatibility with the control-plane / execution-plane split

Use this file when you need high-level context for the VG-SOPD direction or
historical design assumptions behind staged training work.

Do not use it as the first-stop explanation of the current product surface.
For current user-facing behavior, prefer:

- [../getting-started.md](../getting-started.md)
- [../official-examples.md](../official-examples.md)
- [../architecture.md](../architecture.md)

The detailed historical draft is preserved in repository history if you need the
full earlier text.
