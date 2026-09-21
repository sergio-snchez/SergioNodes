# UPSTREAM de cada nodo: constante UPSTREAM en su fichero / tabla en ORIGINS.md.
# Uso: al pedir "check de updates", comparar contra el repo upstream indicado.
WEB_DIRECTORY = "./web"

from .resolution_selector import (
    NODE_CLASS_MAPPINGS as RESOLUTION_CLASS_MAPPINGS,
    NODE_DISPLAY_NAME_MAPPINGS as RESOLUTION_DISPLAY_MAPPINGS,
)

from .ksampler_config import (
    NODE_CLASS_MAPPINGS as KSAMPLER_CLASS_MAPPINGS,
    NODE_DISPLAY_NAME_MAPPINGS as KSAMPLER_DISPLAY_MAPPINGS,
)

from .gguf_nodes import (
    NODE_CLASS_MAPPINGS as GGUF_CLASS_MAPPINGS,
    NODE_DISPLAY_NAME_MAPPINGS as GGUF_DISPLAY_MAPPINGS,
)

from .multilora_loader import (
    NODE_CLASS_MAPPINGS as MULTILORA_CLASS_MAPPINGS,
    NODE_DISPLAY_NAME_MAPPINGS as MULTILORA_DISPLAY_MAPPINGS,
)

from .nkd_face_rig import NKDFaceRig
from . import nkd_face_rig_routes  # noqa: F401 — registers /nkd/facerig/*
from .trix_bypasser import TrixBypasser, TrixBypasserSimple
from .preview_video import PreviewVideo
from .compare_videos import (
    NODE_CLASS_MAPPINGS as COMPARE_CLASS_MAPPINGS,
    NODE_DISPLAY_NAME_MAPPINGS as COMPARE_DISPLAY_MAPPINGS,
)
from .minimax_h3_upscaler_3d import (
    NODE_CLASS_MAPPINGS as MINIMAXH3_CLASS_MAPPINGS,
    NODE_DISPLAY_NAME_MAPPINGS as MINIMAXH3_DISPLAY_MAPPINGS,
)

from .nodes import DLSS5EnhanceImages, DLSS5EnhanceVideoFile, DLSS5SettingsNode

DLSS5_CLASS_MAPPINGS = {
    "DLSS5Settings": DLSS5SettingsNode,
    "DLSS5EnhanceImages": DLSS5EnhanceImages,
    "DLSS5EnhanceVideoFile": DLSS5EnhanceVideoFile,
}
DLSS5_DISPLAY_MAPPINGS = {
    "DLSS5Settings": "DLSS5 Settings",
    "DLSS5EnhanceImages": "DLSS5 Enhance Images",
    "DLSS5EnhanceVideoFile": "DLSS5 Enhance Video File",
}

FACERIG_CLASS_MAPPINGS = {
    "NKDFaceRig": NKDFaceRig,
}

TRIX_CLASS_MAPPINGS = {
    "TrixBypasser": TrixBypasser,
    "TrixBypasserSimple": TrixBypasserSimple,
}

PREVIEW_VIDEO_CLASS_MAPPINGS = {
    "PreviewVideo": PreviewVideo,
    "SergioNodes_PreviewVideo": PreviewVideo,
}
PREVIEW_VIDEO_DISPLAY_MAPPINGS = {
    "PreviewVideo": "Preview Video",
    "SergioNodes_PreviewVideo": "Preview Video",
}

NODE_CLASS_MAPPINGS = {
    **RESOLUTION_CLASS_MAPPINGS,
    **KSAMPLER_CLASS_MAPPINGS,
    **GGUF_CLASS_MAPPINGS,
    **MULTILORA_CLASS_MAPPINGS,
    **FACERIG_CLASS_MAPPINGS,
    **TRIX_CLASS_MAPPINGS,
    **PREVIEW_VIDEO_CLASS_MAPPINGS,
    **COMPARE_CLASS_MAPPINGS,
    **MINIMAXH3_CLASS_MAPPINGS,
    **DLSS5_CLASS_MAPPINGS,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    **RESOLUTION_DISPLAY_MAPPINGS,
    **KSAMPLER_DISPLAY_MAPPINGS,
    **GGUF_DISPLAY_MAPPINGS,
    **MULTILORA_DISPLAY_MAPPINGS,
    **PREVIEW_VIDEO_DISPLAY_MAPPINGS,
    **COMPARE_DISPLAY_MAPPINGS,
    **MINIMAXH3_DISPLAY_MAPPINGS,
    **DLSS5_DISPLAY_MAPPINGS,
}

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS']