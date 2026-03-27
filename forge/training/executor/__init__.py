"""Training executors — run training scripts on various compute backends.

Executors handle the mechanics of deploying and running training scripts
on different compute backends (Targon serverless, SSH, local).

They wrap compute/ backends with training-specific logic.
"""

from forge.training.executor.base import ExecutorProtocol

__all__ = ["ExecutorProtocol"]
