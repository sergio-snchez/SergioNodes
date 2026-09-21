"""ComfyUI nodes exposed by ComfyUI-DLSS5-Enhancer."""

# UPSTREAM: ComfyUI-DLSS5-Enhancer (https://github.com/Blueforcer/ComfyUI-DLSS5-Enhancer) — registro del subpack
from .enhance_images import DLSS5EnhanceImages
from .enhance_video import DLSS5EnhanceVideoFile
from .settings_node import DLSS5SettingsNode

__all__ = ["DLSS5EnhanceImages", "DLSS5EnhanceVideoFile", "DLSS5SettingsNode"]
