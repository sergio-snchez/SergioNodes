# coding: utf-8
"""
😺SergioNodes MiniMax H3 Merge Project — fusiona los chunks de un proyecto.

Aquí es donde la matemática deja de ser teoría. La fusión hace:

    video = chunk_1[0:L]  ++  chunk_2[lf:L]  ++  chunk_3[lf:L]  ++  ...

descartando de cada chunk posterior los `lf` tokens que el ancla hizo que
reprodujera del chunk anterior. El resultado es un AV latent que:

  - cumple la rejilla 17k+5 en frames reales,
  - cumple `latent_t % 5 == 2`, que es lo que el DiT acepta,
  - tiene el audio en `round(frames * 5/3)`,
  - y tiene cada costura en fase, porque `lf ≡ 2 (mod 5)` hace que el fase del
    chunk recortado coincida con la del latente fusionado token a token.

Sobre el audio: los dos streams comparten un único eje temporal, y cada corte
redondea por su cuenta (`round()`), así que concatenar los slices suma una
deriva de uno o dos frames. El nodo no la deja pasar: ajusta el último chunk
para que el total sea exactamente `round(frames * 5/3)` y dice en el informe
cuánto tuvo que ajustar.

Lo que este nodo **no** puede hacer: arreglar una costura que ya es mala en el
origen. La garantía es de *estructura*, no de calidad: el latent fusionado es
legal y se decodifica sin artefactos de concatenación, pero si el contenido no
casaba con el ancla, esa diferencia sigue ahí.
"""
from __future__ import annotations

UPSTREAM = None  # nodo original de SergioNodes (sin upstream; ningún nodo nativo persiste y fusiona chunks)

import time

import torch
from comfy_api.latest import io

from . import h3_chunks as H


class MinimaxH3MergeProject(io.ComfyNode):
    """Merge stored chunks into a single valid MiniMax H3 AV latent."""

    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="MinimaxH3MergeProject",
            display_name="Minimax H3 Merge Project",
            category="Sergio Nodes",
            search_aliases=[
                "h3 merge",
                "merge chunks h3",
                "fusionar h3",
                "unir chunks h3",
                "h3 long merge",
            ],
            description=(
                "Merges the stored chunks of a project into one AV latent, removing the anchor "
                "overlap so the result lands exactly on the model's 17k+5 frame grid. The audio track "
                "is reconciled to round(frames * 5/3) so no rounding drift accumulates. Missing chunk "
                "indices inside the range are skipped and reported."
            ),
            is_output_node=True,
            inputs=[
                io.String.Input("project", default="h3_project", multiline=False,
                                tooltip="Project handle coming from Minimax H3 Project."),
                io.Int.Input("first_index", default=1, min=1, max=9999,
                             tooltip="First chunk to include."),
                io.Int.Input("last_index", default=0, min=0, max=9999,
                             tooltip="Last chunk to include. 0 means 'every chunk from first_index on'."),
                io.Int.Input("anchor_override", default=-1, min=-1, max=12,
                             tooltip="Force a different overlap for all joins, in latent frames. -1 uses "
                                     "the value each chunk recorded when it was generated. Only change "
                                     "this if you know the chunks really do share that much overlap."),
                io.String.Input("output_name", default="merged", multiline=False,
                                tooltip="Base name for the report/UI reference. Nothing is written to disk."),
            ],
            outputs=[
                io.Latent.Output(display_name="LATENT",
                                 tooltip="Merged AV latent. Feed to a video VAE decode + audio decode."),
                io.Int.Output("frames", tooltip="Real frames of the merged video."),
                io.Float.Output("duration_seconds", tooltip="Merged duration at 24 fps."),
                io.String.Output("report", tooltip="Exactly what was cut and why."),
            ],
        )

    @classmethod
    def execute(cls, project, first_index, last_index, anchor_override=-1, output_name="merged") -> io.NodeOutput:
        directory = H.project_dir(project)
        data = H.read_index(directory)
        available = H.existing_indexes(data)
        if not available:
            raise ValueError("El proyecto '{}' no tiene chunks guardados.".format(data.get("name", project)))

        high = available[-1] if int(last_index) <= 0 else int(last_index)
        wanted = [i for i in available if int(first_index) <= i <= high]
        if not wanted:
            raise ValueError("No hay chunks entre {} y {} (disponibles: {}).".format(
                first_index, high, available))

        entries = [H.index_entry(data, i) for i in wanted]
        plan = H.plan_merge(entries, anchor_override if int(anchor_override) >= 0 else None)

        notes = []
        skipped = sorted(set(range(min(wanted), max(wanted) + 1)) - set(wanted))
        if skipped:
            notes.append("Indices ausentes en el rango, omitidos: {}".format(skipped))
        if len(plan["distinct_anchors"]) > 1:
            notes.append("Los chunks usaron anclas distintas {}; se respetó la de cada uno. "
                         "Fusiona sin costuras dobles solo si coinciden.".format(plan["distinct_anchors"]))

        videos, audios = [], []
        for entry in entries:
            video, audio = H.load_chunk_entry(directory, entry)
            videos.append(video)
            audios.append(audio)
        H.check_same_canvas(videos, "MinimaxH3MergeProject")

        merged_video, merged_audio = H.apply_merge(videos, audios, plan)
        problems = H.validate_merged(merged_video, merged_audio, plan)
        if problems:
            raise ValueError("La fusión no produjo un latente válido:\n  - " + "\n  - ".join(problems))

        if plan["audio_drift"] != 0:
            notes.append("Audio: se ajustó el último chunk en {} frames latentes para que el total "
                         "sea exactamente round({}*{}/{}) = {}.".format(
                             abs(plan["audio_drift"]), plan["total_frames"],
                             H.AUDIO_LATENT_FPS, H.FPS, plan["total_audio_t"]))

        if plan["total_frames"] > 362:
            notes.append("AVISO: {} frames superan los ~362 (15.1s) que el modelo fue entrenado a "
                         "generar en una sola pasada. Más allá de eso la calidad es territorio sin "
                         "validar.".format(plan["total_frames"]))

        report_lines = [
            "Fusión de '{}' -> '{}'".format(data.get("name", project), output_name),
            "Chunks: {}".format(wanted),
            "Solapes (tokens latentes): {}".format(plan["anchors"]),
            "",
            "{:<7} {:>6} {:>8} {:>9} {:>9} {:>10}".format(
                "chunk", "frames", "descarta", "tokens", "audio_t", "cursor"),
        ]
        for step, astep in zip(plan["video"], plan["audio"]):
            drop_v = step["latent_slice"][0]
            drop_a = astep["audio_slice"][0]
            entry = next(e for e in entries if int(e["index"]) == step["index"])
            report_lines.append("{:<7} {:>6} {:>8} {:>9} {:>9} {:>10}".format(
                "#{}".format(step["index"]), int(entry["frames"]),
                "{}t/{}f".format(drop_v, H.frames_for_latent_t(drop_v) if drop_v else 0),
                step["keep_frames"], astep["keep_frames"],
                "v{}/a{}".format(step["start_latent"], astep["start_audio"])))
        report_lines += [
            "",
            "TOTAL: {} frames ({:.2f}s), latent_t={}, audio_t={}, {}x{}".format(
                plan["total_frames"], plan["seconds"], plan["total_latent_t"],
                plan["total_audio_t"], int(videos[0].shape[-1]) * 16, int(videos[0].shape[-2]) * 16),
            "Rejilla 17k+5: OK | latent_t % 5 == 2: OK | audio == round(frames*5/3): OK | costuras en fase: OK",
        ]
        report_lines += notes

        return io.NodeOutput(
            H.build_av_latent(merged_video, merged_audio),
            plan["total_frames"],
            plan["seconds"],
            "\n".join(report_lines),
            ui={"sergio_h3_merged": [str(plan["total_frames"])]},
        )
