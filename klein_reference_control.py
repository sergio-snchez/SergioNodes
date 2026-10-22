# coding: utf-8
"""
SergioNodes clone of NKD Klein Reference Control.

Cloned node (same node_id/display name for workflow compatibility):
  NKDKleinReferenceControl -> "Klein Reference Control"
"""
from __future__ import annotations

UPSTREAM = ("NKD Klein Tools", "https://github.com/Nekodificador/ComfyUI-NKD-Klein-Tools", "NKDKleinReferenceControl")

from .klein_tools.region_schedule import NKDKleinReferenceControl

NODE_CLASS_MAPPINGS = {
    "NKDKleinReferenceControl": NKDKleinReferenceControl,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "NKDKleinReferenceControl": "Klein Reference Control",
}
