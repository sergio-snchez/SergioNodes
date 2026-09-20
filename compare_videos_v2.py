# coding: utf-8
"""
😺SergioNodes Compare Videos v2 — A/B slider comparison in the browser.

Normalizes two videos to a common resolution, frame rate and length, writes
each to a temp asset, and hands both previews to a frontend widget that
overlays them with a draggable A/B slider.

Mirrors the stock "Compare Images" node (slider interface), but for videos.
"""
from __future__ import annotations

from comfy_api.latest import io, InputImpl, Types

from .compare_videos import (
    _fit_panel,
    _match_length,
    _resample_frames,
    _safe_color_space,
    _to_frames,
)


class CompareVideosV2(io.ComfyNode):
    """Compare two videos with a draggable A/B slider in the browser."""

    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="CompareVideosV2",
            display_name="Compare Videos v2",
            search_aliases=[
                "A/B video",
                "video A/B",
                "video slider",
                "before after video",
                "video compare v2",
            ],
            category="Sergio Nodes",
            description=(
                "Compare two videos with a draggable A/B slider in the browser. "
                "Both are normalized to the same resolution, frame rate and length."
            ),
            # An output node so the "Run to selected node" play button works
            # without wiring outputs into a preview or save node.
            is_output_node=True,
            inputs=[
                io.Video.Input("video_a", optional=True, tooltip="Left side of the slider (A)."),
                io.Video.Input("video_b", optional=True, tooltip="Right side of the slider (B)."),
                io.Combo.Input(
                    "duration",
                    options=["min", "max"],
                    default="min",
                    tooltip="Compare only the overlap ('min'), or keep the full length of the longer "
                    "video (the shorter one holds its last frame).",
                ),
                io.Combo.Input(
                    "audio",
                    options=["none", "video_a", "video_b"],
                    default="none",
                    tooltip="Soundtrack to place on the right-hand (B) video, which is the only one "
                    "with visible controls; the left side is always muted for the slider.",
                ),
            ],
            # Like the stock Compare Images node: a viewer, no value outputs.
            outputs=[],
        )

    @classmethod
    def execute(
        cls,
        video_a: io.Video.Type = None,
        video_b: io.Video.Type = None,
        duration: str = "min",
        audio: str = "none",
    ) -> io.NodeOutput:
        available = [v for v in (video_a, video_b) if v is not None]
        if not available:
            raise ValueError("Connect at least one video to the Compare Videos v2 node.")

        if len(available) == 1:
            single = available[0]
            result = {"a_video": _save_preview(single), "b_video": []}
            return io.NodeOutput(ui=result)

        images_a, fps_a = _to_frames(video_a)
        images_b, fps_b = _to_frames(video_b)

        base_fps = float(fps_a if float(fps_a) >= float(fps_b) else fps_b)
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

        images_a = _fit_panel(images_a, panel_w, panel_h)
        images_b = _fit_panel(images_b, panel_w, panel_h)

        selected_audio = None
        if audio == "video_a":
            selected_audio = video_a.get_components().audio
        elif audio == "video_b":
            selected_audio = video_b.get_components().audio
        # The Bottom (B) video is the audible one — it is the only one with
        # visible native controls in the slider widget, so the chosen soundtrack
        # goes there regardless of which source it came from.
        vid_bottom = InputImpl.VideoFromComponents(
            Types.VideoComponents(
                images=images_b,
                audio=selected_audio,
                frame_rate=base_fps,
            ),
            bit_depth=video_a.get_bit_depth(),
            color_space=_safe_color_space(video_a.get_color_space()),
        )
        # The Top (A) video is always muted by the frontend, so no audio here.
        vid_top = InputImpl.VideoFromComponents(
            Types.VideoComponents(
                images=images_a,
                audio=None,
                frame_rate=base_fps,
            ),
            bit_depth=video_a.get_bit_depth(),
            color_space=_safe_color_space(video_a.get_color_space()),
        )

        result = {"a_video": _save_preview(vid_top), "b_video": _save_preview(vid_bottom)}
        return io.NodeOutput(ui=result)


def _save_preview(video: io.Video.Type) -> list:
    from comfy_extras.nodes_video import save_video_preview

    return save_video_preview(video).values


NODE_CLASS_MAPPINGS = {
    "CompareVideosV2": CompareVideosV2,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "CompareVideosV2": "Compare Videos v2",
}