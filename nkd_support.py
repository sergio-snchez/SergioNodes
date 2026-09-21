"""
Small support functions for the Face Rig node, extracted from the upstream
pack's `helpers`: nothing else from that module (text splitting, masks, color
math) is used by the rig.
"""
from __future__ import annotations

UPSTREAM = ("😺NKD Basic Tools (helpers del Face Rig)", "https://github.com/Nekodificador/ComfyUI-NKD-Basic-Tools", "modalidades internas del port")

import numpy as np

# Last frame pushed per node, kept so the rig's preview route has something to
# work on without the graph running again.
_SOURCE_CACHE: "dict[str, tuple[int, int, bytes, int]]" = {}
_SOURCE_CACHE_MAX = 8
_MASK_CACHE: "dict[str, object]" = {}


def node_id(cls, supplied=None):
    """The id of the executing node.

    The V3 API delivers hidden inputs on `cls.hidden`, NOT as kwargs to
    execute - declaring `hidden=[io.Hidden.unique_id]` and then reading a
    `unique_id=None` parameter silently yields None, and every websocket push
    keyed by node id goes nowhere. `supplied` keeps the older kwarg working.
    """
    return supplied or getattr(getattr(cls, "hidden", None), "unique_id", None)


def push_source(unique_id, image, event: str = "nkd-source", max_side: int = 1024,
                mask=None) -> None:
    """Push the first frame of `image` to the frontend as raw base64 RGB.

    The rig editor needs a backdrop even when the source is computed (a VAE
    Decode has no thumbnail until it runs), so the node sends the pixels it
    has, keyed by node id. The frontend caches the frame and the preview route
    renders on top of it. Raw RGB bytes rather than a PNG: no encoder on the
    way out, no decoder on the way in. Never raises - a missing backdrop must
    not fail a render.
    """
    if unique_id is None:
        return
    try:
        import base64
        from server import PromptServer

        frame = image[0] if hasattr(image, "shape") and len(image.shape) == 4 else image
        if hasattr(frame, "detach"):
            frame = frame.detach().cpu().numpy()
        frame = np.clip(np.asarray(frame, dtype=np.float32), 0.0, 1.0)[:, :, :3]
        full_h, full_w = frame.shape[:2]

        longest = max(frame.shape[:2])
        if longest > max_side:
            step = int(np.ceil(longest / max_side))
            frame = frame[::step, ::step]
        h, w = frame.shape[:2]
        buf = (frame * 255.0 + 0.5).astype(np.uint8).tobytes()

        if len(_SOURCE_CACHE) >= _SOURCE_CACHE_MAX:
            drop = next(iter(_SOURCE_CACHE))
            _SOURCE_CACHE.pop(drop)
            _MASK_CACHE.pop(drop, None)
        # full_w travels with it: preview settings in pixels of the rendered
        # image need the ratio to scale down to the pushed frame.
        _SOURCE_CACHE[str(unique_id)] = (h, w, buf, full_w)

        if mask is None:
            _MASK_CACHE.pop(str(unique_id), None)
        else:
            m = mask.detach()
            _MASK_CACHE[str(unique_id)] = (m if m.dim() == 3 else m.unsqueeze(0))[:1].cpu()

        PromptServer.instance.send_sync(event, {
            "node": str(unique_id),
            "width": w, "height": h,
            "full_width": full_w, "full_height": full_h,
            "data": base64.b64encode(buf).decode("ascii"),
        })
    except Exception:
        pass