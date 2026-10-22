# coding: utf-8
"""
SergioNodes clone of selected H3 Relay nodes.

Cloned nodes (same node_id/display name for workflow compatibility):
  LabsH3PrepareVideo      -> "H3 Prepare Video - Auto Size & Length"
  H3RelayWindowedEdit    -> "H3 Relay Windowed Edit - Character Swap"
"""
from __future__ import annotations

UPSTREAM = ("H3 Relay", "https://github.com/akatz-ai/h3-relay", "H3Relay")

from .h3_relay.video_prep import LabsH3PrepareVideo
from .h3_relay.windowed_edit import (
    H3RelayWindowedEdit,
    H3RelayEditWindow,
    H3RelayEditHistory,
    H3RelayEditAppend,
)
from .h3_relay.person_remover import H3RelayRemovalRestore

# Register H3 Relay HTTP routes (staged assembly + removal previews) when possible.
try:
    from .h3_relay.staged import register_routes as _register_staged_routes
    from .h3_relay.removal_previews import register_routes as _register_removal_routes
    _register_staged_routes()
    _register_removal_routes()
except Exception:
    pass

NODE_CLASS_MAPPINGS = {
    "LabsH3PrepareVideo": LabsH3PrepareVideo,
    "H3RelayWindowedEdit": H3RelayWindowedEdit,
    # Internal helper nodes required by Windowed Edit's dynamic graph.
    "H3RelayEditWindow": H3RelayEditWindow,
    "H3RelayEditHistory": H3RelayEditHistory,
    "H3RelayEditAppend": H3RelayEditAppend,
    "H3RelayRemovalRestore": H3RelayRemovalRestore,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "LabsH3PrepareVideo": "H3 Prepare Video - Auto Size & Length",
    "H3RelayWindowedEdit": "H3 Relay Windowed Edit - Character Swap",
    "H3RelayEditWindow": "H3 Relay Edit Window",
    "H3RelayEditHistory": "H3 Relay Edit History",
    "H3RelayEditAppend": "H3 Relay Edit Append",
    "H3RelayRemovalRestore": "H3 Relay Removal Restore",
}
