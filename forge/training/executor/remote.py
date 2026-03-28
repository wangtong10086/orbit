"""Remote SSH executor — runs training on SSH-accessible instances.

Wraps forge.compute.ssh with training-specific logic:
- Upload script via SCP
- Launch in screen session
- Monitor via log file (using external shell template)
"""

from __future__ import annotations

from forge.compute.base import GpuInstance
from forge.config import ForgeConfig
from forge.training.templates import load_template


class RemoteExecutor:
    """Execute training on SSH-accessible GPU instances."""

    def __init__(self, config: ForgeConfig):
        self.config = config

    async def launch(
        self,
        script: str,
        dataset_path: str,
        env_name: str,
        instance: GpuInstance,
        **kwargs,
    ) -> GpuInstance:
        """Upload script and launch training on SSH instance."""
        from forge.compute.manager import ComputeManager

        # Write script locally
        local_script = "/tmp/train_sft.py"
        with open(local_script, "w") as f:
            f.write(script)

        compute = ComputeManager(self.config)
        be = compute.get_backend("ssh")
        await be.upload(instance, local_script, "/root/scripts/train_sft.py")

        # Launch in screen session
        cmd = (
            "screen -dmS training bash -c "
            "'python3 /root/scripts/train_sft.py 2>&1 | tee /root/training.log'"
        )
        rc, stdout, stderr = await be.exec(instance, cmd, timeout=30)

        if rc == 0:
            print(f"Training launched on {instance.host}")
        else:
            print(f"Failed to launch: {stderr}")

        return instance

    async def monitor(self, instance: GpuInstance) -> dict:
        """Get training status from SSH instance via log and GPU stats."""
        from forge.compute.manager import ComputeManager

        compute = ComputeManager(self.config)
        be = compute.get_backend("ssh")

        monitor_script = load_template("monitor_ssh.sh")
        rc, stdout, stderr = await be.exec(instance, monitor_script, timeout=30)
        return {"output": stdout, "error": stderr, "returncode": rc}

    async def stop(self, instance: GpuInstance) -> None:
        """Kill the training screen session."""
        from forge.compute.manager import ComputeManager

        compute = ComputeManager(self.config)
        be = compute.get_backend("ssh")
        await be.exec(instance, "screen -S training -X quit", timeout=10)
