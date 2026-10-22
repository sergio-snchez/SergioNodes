# coding: utf-8
"""
SergioNodes clone of NKD Klein Presampling and Postsampling.

Cloned nodes (same node_id/display name for workflow compatibility):
  NKDKleinPresampling  -> "Klein Presampling"
  NKDKleinPostsampling -> "Klein Postsampling"
"""
from __future__ import annotations

UPSTREAM = ("NKD Klein Tools", "https://github.com/Nekodificador/ComfyUI-NKD-Klein-Tools", "NKDKleinPresampling")

from .klein_tools.nodes import NKDKleinPresampling

NODE_CLASS_MAPPINGS = {
    "NKDKleinPresampling": NKDKleinPresampling,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "NKDKleinPresampling": "Klein Presampling",
}
