# coding: utf-8
"""
SergioNodes clone of selected MiniMax H3 RefMod nodes from ComfyUI-MiniMaxH3Mod.

Cloned nodes (same node_id/display name for workflow compatibility):
  MiniMaxH3RefModMasterExtract -> "Create H3 RefMod Master"
  MiniMaxH3RefModInspect      -> "Inspect H3 RefMod"
  MiniMaxH3RefModsLoader      -> "Load H3 RefMods"
  MiniMaxH3RefModSave         -> "Save H3 RefMods"
  MiniMaxH3RefModApply        -> "Apply H3 RefMod"
"""
from __future__ import annotations

UPSTREAM = ("ComfyUI-MiniMaxH3Mod", "https://github.com/Luisacaotica/ComfyUI-MiniMaxH3Mod", "MiniMaxH3RefMod")

from .minimax_h3_refmod.nodes import (
    MiniMaxH3RefModMasterExtract,
    MiniMaxH3RefModInspect,
    MiniMaxH3RefModsLoader,
    MiniMaxH3RefModSave,
    MiniMaxH3RefModApply,
)

NODE_CLASS_MAPPINGS = {
    "MiniMaxH3RefModMasterExtract": MiniMaxH3RefModMasterExtract,
    "MiniMaxH3RefModInspect": MiniMaxH3RefModInspect,
    "MiniMaxH3RefModsLoader": MiniMaxH3RefModsLoader,
    "MiniMaxH3RefModSave": MiniMaxH3RefModSave,
    "MiniMaxH3RefModApply": MiniMaxH3RefModApply,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "MiniMaxH3RefModMasterExtract": "Create H3 RefMod Master",
    "MiniMaxH3RefModInspect": "Inspect H3 RefMod",
    "MiniMaxH3RefModsLoader": "Load H3 RefMods",
    "MiniMaxH3RefModSave": "Save H3 RefMods",
    "MiniMaxH3RefModApply": "Apply H3 RefMod",
}