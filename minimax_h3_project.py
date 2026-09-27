# coding: utf-8
"""
😺SergioNodes MiniMax H3 Project — abre o crea un proyecto de vídeo largo por chunks.

Este nodo no tiene entradas: solo widgets. Su trabajo es resolver un nombre de
proyecto a una carpeta en disco y decirte qué hay dentro, para que los otros tres
nodos de la serie (Anchor, Vault y Merge) se refieran siempre al mismo sitio.

Los proyectos viven en:

    ComfyUI/output/h3_projects/<nombre>/project.json      (índice)
    ComfyUI/output/h3_projects/<nombre>/chunk_0001.safetensors
    ...

Guardar cada chunk por separado (en vez de mantener un único latent en memoria)
es lo que permite generar un vídeo largo en sesiones separadas: puedes cerrar
ComfyUI entre chunk y chunk y seguir mañana donde lo dejaste.
"""
from __future__ import annotations

UPSTREAM = None  # nodo original de SergioNodes (sin upstream; cubre la gestión de proyecto que los nodos H3 nativos no tienen)

import os

from comfy_api.latest import io

from . import h3_chunks as H


def _mb(num_bytes) -> float:
    return round(int(num_bytes) / (1024.0 * 1024.0), 2)


class MinimaxH3Project(io.ComfyNode):
    """Open or create an on-disk project that holds the chunks of a long H3 video."""

    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="MinimaxH3Project",
            display_name="Minimax H3 Project",
            category="Sergio Nodes",
            search_aliases=[
                "h3 project",
                "minimax project",
                "h3 long video",
                "proyecto h3",
                "proyecto video largo",
            ],
            description=(
                "Opens or creates an on-disk project where each generated chunk is stored as a "
                "safetensors file, so a long MiniMax H3 video can be produced across separate runs."
            ),
            is_output_node=True,
            inputs=[
                io.String.Input("project_name", default="h3_project", multiline=False,
                                tooltip="Project folder name. Only letters, digits, spaces, _ and - are kept."),
                io.Boolean.Input("create_if_missing", default=True,
                                 tooltip="Create the folder if it does not exist. Turn off to fail instead."),
                io.Boolean.Input("reset_index", default=False,
                                 tooltip="DANGER: clears the index and forgets every stored chunk. "
                                         "The .safetensors files stay on disk but become orphans."),
            ],
            outputs=[
                io.String.Output("project", tooltip="Project handle to wire into the other H3 nodes."),
                io.String.Output("path", tooltip="Absolute folder path."),
                io.Int.Output("next_index", tooltip="First free chunk index."),
                io.Int.Output("chunk_count", tooltip="How many chunks are stored."),
                io.String.Output("report", tooltip="Human readable summary."),
            ],
        )

    @classmethod
    def execute(cls, project_name="h3_project", create_if_missing=True, reset_index=False) -> io.NodeOutput:
        name = H.sanitize_project_name(project_name)
        exists = name in H.list_projects()

        if not exists and not create_if_missing:
            available = H.list_projects()
            hint = ", ".join(available) if available else "(ninguno)"
            raise ValueError(
                "El proyecto '{}' no existe. Proyectos disponibles: {}. "
                "Activa create_if_missing o usa uno de esos nombres.".format(name, hint))

        directory = H.project_dir(name, create=True)

        if reset_index:
            data = H.blank_index(name)
            H.write_index(directory, data)
        else:
            data = H.read_index(directory)

        chunks = H.existing_indexes(data)
        total_frames = sum(int(e.get("frames", 0)) for e in data.get("chunks", []))
        size = H.project_bytes(data)

        report_lines = [
            "Proyecto: {}".format(name),
            "Ruta: {}".format(directory),
            "Chunks: {} {}".format(len(chunks), chunks if chunks else "(ninguno)"),
            "Siguiente índice libre: {}".format(H.next_free_index(data)),
            "Tamaño en disco: {} MiB".format(_mb(size)),
        ]
        if total_frames:
            report_lines.append("Suma de duraciones: {} frames ({:.2f}s) — remember esto todavía "
                                "incluye el solape de las costuras.".format(
                                    total_frames, H.frames_to_seconds(total_frames)))
        for entry in sorted(data.get("chunks", []), key=lambda e: int(e.get("index", 0))):
            report_lines.append("  #{:<3d} {:>4d}f ({:.2f}s)  lat_t={:<4d} audio_t={:<4d} ancla={:<3d} {}".format(
                int(entry.get("index", 0)), int(entry.get("frames", 0)),
                H.frames_to_seconds(int(entry.get("frames", 0))),
                int(entry.get("latent_t", 0)), int(entry.get("audio_t", 0)),
                int(entry.get("anchor_latent_frames", 0)), entry.get("file", "")))
        if not exists:
            report_lines.append("(carpeta recién creada)")

        return io.NodeOutput(
            name,
            directory,
            H.next_free_index(data),
            len(chunks),
            "\n".join(report_lines),
            ui={"sergio_h3_project": [name]},
        )
