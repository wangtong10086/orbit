"""Compatibility wrapper for the remote machine CLI.

The active implementation now lives in ``forge.remote_ops.machine``.
"""

from forge.remote_ops.machine import machine as rental

__all__ = ["rental"]
