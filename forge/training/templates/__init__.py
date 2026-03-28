"""Load shell templates from the templates/ directory."""

from pathlib import Path

_TEMPLATE_DIR = Path(__file__).parent


def load_template(name: str) -> str:
    """Read a shell template file by name.

    Args:
        name: Template filename (e.g. "targon_train.sh")

    Returns:
        Template content as string.

    Raises:
        FileNotFoundError: If template does not exist.
    """
    path = _TEMPLATE_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Template not found: {path}")
    return path.read_text()


def render_targon_command(
    dataset_hf_repo: str,
    dataset_file: str,
    swift_cmd: str,
    config_file: str = "swift_config.yaml",
) -> str:
    """Render the Targon container bash entrypoint command.

    Instead of embedding a 80-line bash string inline, this reads the
    targon_train.sh template which expects env vars at runtime:
      DATASET_HF_REPO, DATASET_FILE, SWIFT_CMD, HF_TOKEN, HF_BACKUP_REPO

    Returns:
        A single bash -c compatible command string that sources the template.
    """
    # The template reads env vars at runtime, so we inject the
    # non-secret values as env vars in the container config.
    # The command just executes the script from stdin.
    script = load_template("targon_train.sh")
    script = script.replace("swift_config.yaml", config_file)
    # Escape single quotes for bash -c '...' wrapping
    escaped = script.replace("'", "'\\''")
    return f"bash -c '{escaped}'"
