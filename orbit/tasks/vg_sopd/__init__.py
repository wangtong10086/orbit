"""VG-SOPD staged workflow support."""

from orbit.tasks.vg_sopd.compile_plugin import VGCompilePlugin
from orbit.tasks.vg_sopd.frontier_plugin import VGFrontierPlugin
from orbit.tasks.vg_sopd.relabel_plugin import VGRelabelPlugin

__all__ = ["VGCompilePlugin", "VGFrontierPlugin", "VGRelabelPlugin"]
