# coding: utf-8
"""
😺SergioNodes Compare Videos — combine two videos into a single comparison video.

Merges two VIDEO streams into one comparison video so both play at the same
time: side by side (left/right) or stacked (top/bottom). Frames are time
synchronized (the shorter video holds its last frame when "max" duration is
selected), both are resampled to a common frame rate, and the result is
returned as a normal VIDEO that can be previewed in canvas or saved.

Mirrors the stock "Compare Images" node, but for videos.
"""
from __future__ import annotations

UPSTREAM = None  # nodo original de SergioNodes (espeja el Compare Images nativo, pero para vídeo)

from fractions import Fraction

import torch
import torch.nn.functional as F
from comfy_api.latest import io, InputImpl, Types

_VALID_COLOR_SPACES = ("sRGB", "HDR", "HDR PQ")


def _to_frames(video: io.Video.Type) -> tuple[torch.Tensor, object]:
    components = video.get_components()
    return components.images, components.frame_rate


def _resample_frames(images: torch.Tensor, src_fps: float, dst_fps: float) -> torch.Tensor:
    """Resample a (F, H, W, 3) tensor to a different playback frame rate."""
    if dst_fps == src_fps or images.shape[0] <= 1:
        return images
    duration = images.shape[0] / src_fps
    count = max(1, int(round(duration * dst_fps)))
    source = torch.arange(count, dtype=torch.float32, device=images.device)
    indices = (source / dst_fps * src_fps).floor().clamp(0, images.shape[0] - 1).long()
    return images[indices]


def _fit_panel(images: torch.Tensor, panel_w: int, panel_h: int) -> torch.Tensor:
    """Letterbox a (F, H, W, 3) tensor into a (F, panel_h, panel_w, 3) canvas."""
    frames, height, width, channels = images.shape
    scale = min(panel_w / width, panel_h / height)
    new_w = min(panel_w, max(2, int(round(width * scale))))
    new_h = min(panel_h, max(2, int(round(height * scale))))
    offset_x = (panel_w - new_w) // 2
    offset_y = (panel_h - new_h) // 2
    resized = images.permute(0, 3, 1, 2)  # (F, C, H, W)
    resized = F.interpolate(
        resized,
        size=(new_h, new_w),
        mode="area" if scale <= 1 else "bilinear",
        align_corners=None if scale <= 1 else False,
    ).permute(0, 2, 3, 1)  # (F, H, W, C)
    canvas = torch.zeros(
        frames, panel_h, panel_w, channels, dtype=images.dtype, device=images.device
    )
    canvas[:, offset_y : offset_y + new_h, offset_x : offset_x + new_w, :] = resized
    return canvas


def _match_length(images: torch.Tensor, count: int) -> torch.Tensor:
    """Trim to `count` frames, or hold the last frame to reach it."""
    if images.shape[0] >= count:
        return images[:count]
    hold = images[-1:].expand(count - images.shape[0], -1, -1, -1)
    return torch.cat([images, hold], dim=0)


class CompareVideos(io.ComfyNode):
    """Combine two videos into one synchronized comparison video."""

    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="CompareVideos",
            display_name="Compare Videos",
            search_aliases=[
                "video compare",
                "compare video",
                "video comparison",
                "side by side video",
                "A/B video",
            ],
            category="Sergio Nodes",
            description=(
                "Combine two videos into one synchronized comparison video: "
                "side by side (left/right) or stacked (top/bottom)."
            ),
            # An output node so the "Run to selected node" play button works
            # without wiring the video output into a preview or save node.
            is_output_node=True,
            inputs=[
                io.Video.Input("video_a", optional=True, tooltip="First video to compare."),
                io.Video.Input("video_b", optional=True, tooltip="Second video to compare."),
                io.Combo.Input(
                    "layout",
                    options=["side by side", "top and bottom"],
                    default="side by side",
                    tooltip="Places video A and B next to each other, or on top of each other.",
                ),
                io.Combo.Input(
                    "duration",
                    options=["min", "max"],
                    default="min",
                    tooltip="Compare only the overlap ('min'), or keep the full length of the longer video "
                    "(the shorter one holds its last frame).",
                ),
                io.Int.Input(
                    "gap",
                    default=4,
                    min=0,
                    max=64,
                    step=2,
                    tooltip="Size of the black divider between the two videos, in pixels.",
                ),
                io.Combo.Input(
                    "audio",
                    options=["none", "video_a", "video_b"],
                    default="none",
                    tooltip="Optional soundtrack for the comparison video.",
                ),
            ],
            outputs=[
                io.Video.Output(
                    "video",
                    tooltip="The combined comparison video. Preview it or send it to a Save Video node.",
                ),
            ],
        )

    @classmethod
    def execute(
        cls,
        video_a: io.Video.Type = None,
        video_b: io.Video.Type = None,
        layout: str = "side by side",
        duration: str = "min",
        gap: int = 4,
        audio: str = "none",
    ) -> io.NodeOutput:
        available = [v for v in (video_a, video_b) if v is not None]
        if not available:
            raise ValueError("Connect at least one video to the Compare Videos node.")
        if len(available) == 1:
            single = available[0]
            return io.NodeOutput(single, ui=_preview(single))

        images_a, fps_a = _to_frames(video_a)
        images_b, fps_b = _to_frames(video_b)

        fps_keep = fps_a if float(fps_a) >= float(fps_b) else fps_b
        base_fps = float(fps_keep)
        if base_fps <= 0:
            raise ValueError("Videos must have a positive frame rate.")

        images_a = _resample_frames(images_a.float(), float(fps_a), base_fps)
        images_b = _resample_frames(images_b.float(), float(fps_b), base_fps)

        frame_count = (
            min(images_a.shape[0], images_b.shape[0])
            if duration == "min"
            else max(images_a.shape[0], images_b.shape[0])
        )
        images_a = _match_length(images_a, frame_count)
        images_b = _match_length(images_b, frame_count)

        panel_w = max(images_a.shape[2], images_b.shape[2])
        panel_h = max(images_a.shape[1], images_b.shape[1])
        panel_w += panel_w % 2
        panel_h += panel_h % 2
        gap -= gap % 2

        images_a = _fit_panel(images_a, panel_w, panel_h)
        images_b = _fit_panel(images_b, panel_w, panel_h)

        if layout == "top and bottom":
            canvas_h = panel_h * 2 + gap
            composite = torch.zeros(frame_count, canvas_h, panel_w, 3, device=images_a.device)
            composite[:, 0:panel_h, :, :] = images_a
            composite[:, panel_h + gap :, :, :] = images_b
        else:
            canvas_w = panel_w * 2 + gap
            composite = torch.zeros(frame_count, panel_h, canvas_w, 3, device=images_a.device)
            composite[:, :, 0:panel_w, :] = images_a
            composite[:, :, panel_w + gap :, :] = images_b

        selected_audio = None
        if audio == "video_a":
            selected_audio = video_a.get_components().audio
        elif audio == "video_b":
            selected_audio = video_b.get_components().audio

        combined = InputImpl.VideoFromComponents(
            Types.VideoComponents(
                images=composite,
                audio=selected_audio,
                frame_rate=fps_keep,
            ),
            bit_depth=video_a.get_bit_depth(),
            color_space=_safe_color_space(video_a.get_color_space()),
        )
        return io.NodeOutput(combined, ui=_preview(combined))


def _safe_color_space(value: object) -> str:
    if value in _VALID_COLOR_SPACES:
        return value  # type: ignore[return-value]
    return "sRGB"


def _preview(video: io.Video.Type):
    from comfy_extras.nodes_video import save_video_preview

    return save_video_preview(video)


NODE_CLASS_MAPPINGS = {
    "CompareVideos": CompareVideos,
    "SergioNodes_CompareVideos": CompareVideos,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "CompareVideos": "Compare Videos",
    "SergioNodes_CompareVideos": "Compare Videos",
}