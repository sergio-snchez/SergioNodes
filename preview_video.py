# coding: utf-8
"""
😺SergioNodes Preview Video — video preview in canvas without saving to permanent output.

Stock ComfyUI provides Save Video (which saves permanently to the output folder)
and Preview Image (which previews images temporarily), but lacks a standalone
Preview Video node. This node fills that gap: it accepts a VIDEO stream (from
Create Video, Load Video, etc.), saves a temporary ultrafast preview to ComfyUI's
temp directory, and displays the interactive video player right inside the node.
"""
from __future__ import annotations

UPSTREAM = None  # nodo original de SergioNodes (sin upstream; cubre el hueco entre Preview Image y Save Video)

import torch
from comfy_api.latest import io


class PreviewVideo(io.ComfyNode):
    """Preview a video in canvas without saving it to the permanent ComfyUI output directory."""

    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="PreviewVideo",
            display_name="Preview Video",
            category="video",
            search_aliases=[
                "preview video",
                "video preview",
                "view video",
                "show video",
                "display video",
                "video viewer",
            ],
            description="Preview the video without saving it to the ComfyUI output directory.",
            is_output_node=True,
            inputs=[
                io.Video.Input("video", tooltip="The video to preview."),
            ],
            outputs=[
                io.Video.Output("video", tooltip="The input video, unchanged (optional passthrough)."),
            ],
        )

    @classmethod
    def execute(cls, video: io.Video.Type) -> io.NodeOutput:
        if video is None:
            return io.NodeOutput(None)

        from comfy_extras.nodes_video import save_video_preview

        # Handle native ComfyUI Input.Video
        if hasattr(video, "save_to"):
            return io.NodeOutput(video, ui=save_video_preview(video))

        # Handle raw image tensor fallback if an IMAGE batch was passed
        if isinstance(video, torch.Tensor):
            from fractions import Fraction
            from comfy_api.latest import InputImpl, Types
            vid = InputImpl.VideoFromComponents(
                Types.VideoComponents(images=video, frame_rate=Fraction(24, 1)),
            )
            return io.NodeOutput(vid, ui=save_video_preview(vid))

        return io.NodeOutput(video)
