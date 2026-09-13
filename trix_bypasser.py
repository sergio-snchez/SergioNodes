# coding: utf-8
"""
😺Sergio Trix Bypass — the TrixBypasser/TrixBypasserSimple control nodes,
ported from comfyui-trixnodes into this package for the modern (V3) node API.

The Python side is deliberately empty: these are pure frontend controllers —
the node has no inputs, no outputs, and executing it changes nothing. All the
work happens in `web/trix_bypasser.js`, which renders the target list inside
the node and applies bypass (mode 4) / mute (mode 2) to the target nodes.

The original pack hooked these classes with the legacy INPUT_TYPES API, which
the modern frontend ignores. Registering them here as V3 nodes with the same
type names keeps old workflows working; disable comfyui-trixnodes so both
extensions do not fight over the same nodes.
"""
from comfy_api.latest import io


class TrixBypasser(io.ComfyNode):
    """List of target nodes grouped, toggling bypass or mute from the canvas."""

    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="TrixBypasser",
            display_name="Bypass Groups by ID",
            category="Sergio Nodes",
            description="Sergio Nodes",
            hidden=[io.Hidden.unique_id],
        )

    @classmethod
    def execute(cls, **kwargs):
        return None


class TrixBypasserSimple(io.ComfyNode):
    """Flat list of target nodes, toggling bypass or mute from the canvas."""

    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="TrixBypasserSimple",
            display_name="Bypass Nodes by ID",
            category="Sergio Nodes",
            description="Sergio Nodes",
            hidden=[io.Hidden.unique_id],
        )

    @classmethod
    def execute(cls, **kwargs):
        return None