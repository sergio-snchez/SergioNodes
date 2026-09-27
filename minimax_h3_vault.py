# coding: utf-8
"""
😺SergioNodes MiniMax H3 Chunk Vault — guarda un chunk en disco y actualiza el índice.

Este nodo es el que convierte "un latent en memoria" en "un chunk persistente".
Se coloca entre el KSampler y el siguiente Chunk Anchor:

    Chunk Anchor -> KSampler -> Chunk Vault -> (siguiente Chunk Anchor)

Importante: la geometría que se registra se lee del **tensor**, no de lo que se
pidió en el nodo Anchor. El tensor es la verdad; si alguien reencadena el anchor
con otro sampler o un latent distinto, el índice refleja lo que realmente se
generó en vez de lo que se quiso pedir.

La política de ancla (cuántos tokens reprodujo del chunk anterior) se toma del
registro `pending` que dejó el nodo Anchor, para que el nodo de fusión no dependa
de un cable extra. Si quieres, puedes saltarte el Anchor y declararla a mano con
`anchor_latent_frames`; el índice siempre refleja lo que se guardó de verdad.
"""
from __future__ import annotations

UPSTREAM = None  # nodo original de SergioNodes (sin upstream; SaveLatent nativo no soporta NestedTensor)

import os
import time

from comfy_api.latest import io

from . import h3_chunks as H


def _mb(num_bytes) -> float:
    return round(int(num_bytes) / (1024.0 * 1024.0), 2)


class MinimaxH3ChunkVault(io.ComfyNode):
    """Store one sampled chunk as a safetensors file and record it in the project index."""

    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="MinimaxH3ChunkVault",
            display_name="Minimax H3 Chunk Vault",
            category="Sergio Nodes",
            search_aliases=[
                "h3 vault",
                "h3 save chunk",
                "h3 store",
                "boveda h3",
                "guardar chunk h3",
            ],
            description=(
                "Saves the sampled AV latent as chunk_NNNN.safetensors inside the project and records "
                "it in the index, so the chunk can be used as the anchor of the next one, merged, or "
                "reopened in a later ComfyUI session. Re-saving the same index overwrites it."
            ),
            is_output_node=True,
            inputs=[
                io.String.Input("project", default="h3_project", multiline=False,
                                tooltip="Project handle coming from Minimax H3 Project."),
                io.Int.Input("chunk_index", default=1, min=1, max=9999,
                             tooltip="Which chunk this latent is. Must match the index used in Chunk Anchor."),
                io.Int.Input("anchor_latent_frames", default=-1, min=-1, max=12,
                             tooltip="Overlap this chunk has with the previous one, in latent frames. "
                                     "-1 uses whatever Chunk Anchor recorded. Set it by hand only if you "
                                     "know the chunk really does replay that many frames; the merge maths "
                                     "depends on it. Chunk 1 is always 0."),
                io.Latent.Input("latent", tooltip="Sampled AV latent from the KSampler."),
            ],
            outputs=[
                io.Latent.Output(display_name="LATENT",
                                 tooltip="The same latent, unchanged. Keeps the chain connected."),
                io.Int.Output("next_index", tooltip="First free chunk index, to feed the next Chunk Anchor."),
                io.Float.Output("saved_mb", tooltip="Size of the written file in MiB."),
                io.String.Output("report", tooltip="What was written where."),
            ],
        )

    @classmethod
    def execute(cls, project, chunk_index, anchor_latent_frames, latent) -> io.NodeOutput:
        index = int(chunk_index)
        override = int(anchor_latent_frames)
        video, audio = H.require_h3_av_latent(latent, "MinimaxH3ChunkVault")
        geometry = H.video_geometry(video)

        directory = H.project_dir(project)
        data = H.read_index(directory)

        notes = []
        if override >= 0 and index == 1:
            notes.append("El chunk 1 no lleva ancla por definición, así que se ignora el valor "
                         "manual de anchor_latent_frames.")

        if override >= 0:
            # declarado a mano: manda sobre lo que anotó el Anchor
            anchor_tokens = H.normalize_anchor_latent_frames(override) if override else 0
            if index == 1:
                anchor_tokens = 0
            pending = {"anchor_latent_frames": anchor_tokens}
        else:
            pending = data.get("pending") or {}
            recorded_anchor = int(pending.get("anchor_latent_frames", 0) or 0)
            if int(pending.get("index", -1)) == index:
                # normaliza por si el índice se editó a mano
                anchor_tokens = H.normalize_anchor_latent_frames(recorded_anchor) if recorded_anchor else 0
            else:
                existing = H.index_entry(data, index)
                if existing is not None:
                    anchor_tokens = int(existing.get("anchor_latent_frames", 0) or 0)
                    pending = existing
                elif index == 1:
                    # El chunk 1 abre la línea de tiempo y por definición no lleva ancla, así
                    # que no hace falta que nadie haya pasado por el nodo Anchor. Esto además
                    # deja importar un chunk 1 generado con los nodos nativos.
                    anchor_tokens = 0
                    pending = {}
                else:
                    raise ValueError(
                        "No hay registro 'pending' del chunk {} en el proyecto '{}'. Conecta antes el nodo "
                        "MinimaxH3ChunkAnchor con chunk_index={} para que quede anotada la política de "
                        "ancla, o pon anchor_latent_frames a mano.".format(
                            index, data.get("name", project), index))

        if not H.is_valid_latent_t(geometry["latent_t"]):
            raise ValueError(
                "El latent tiene {} frames latentes, que no está en la rejilla 5k+2 del modelo. "
                "Pasa por MinimaxH3ChunkAnchor para que la geometría sea válida.".format(geometry["latent_t"]))

        frames = geometry["frames"]
        audio_t = int(audio.shape[-1])
        expected_audio = H.audio_t_for_frames(frames)
        if audio_t != expected_audio:
            notes.append("El audio del latent mide {} frames, se esperaban {} para {} frames de vídeo.".format(
                audio_t, expected_audio, frames))

        path, size = H.save_chunk(directory, index, video, audio, {
            "index": index,
            "frames": frames,
            "latent_t": geometry["latent_t"],
            "audio_t": audio_t,
            "width": geometry["width"],
            "height": geometry["height"],
            "anchor_latent_frames": anchor_tokens,
            "anchor_frames_back": pending.get("anchor_frames_back", 0),
            "anchor_audio_latent_t": pending.get("anchor_audio_latent_t", 0),
            "audio_anchor_mode": pending.get("audio_anchor_mode", ""),
            "has_refs": pending.get("has_refs", False),
            "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        })

        entry = {
            "index": index,
            "file": os.path.basename(path),
            "frames": frames,
            "latent_t": geometry["latent_t"],
            "audio_t": audio_t,
            "width": geometry["width"],
            "height": geometry["height"],
            "anchor_latent_frames": anchor_tokens,
            "anchor_frames_back": pending.get("anchor_frames_back", 0),
            "audio_anchor_mode": pending.get("audio_anchor_mode", ""),
            "has_refs": bool(pending.get("has_refs", False)),
            "prompt": pending.get("prompt", ""),
            "bytes": size,
            "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        replaced = H.index_entry(data, index) is not None
        H.upsert_entry(data, entry)
        data["pending"] = None
        H.write_index(directory, data)

        report_lines = [
            "{} chunk {} -> {}".format("Sustituido" if replaced else "Guardado", index, path),
            "Geometría: {}x{}, {} frames ({:.2f}s), latent_t={}, audio_t={}".format(
                geometry["width"], geometry["height"], frames,
                H.frames_to_seconds(frames), geometry["latent_t"], audio_t),
            "Ancla para este chunk: {} tokens latentes{}".format(
                anchor_tokens, "" if anchor_tokens else " (chunk 1)"),
            "Tamaño: {} MiB | siguiente índice libre: {}".format(_mb(size), H.next_free_index(data)),
        ]
        report_lines += notes
        report_lines.append("Ahora el chunk {} ya puede anclar al chunk {}.".format(index + 1, index))

        return io.NodeOutput(
            latent,
            H.next_free_index(data),
            _mb(size),
            "\n".join(report_lines),
            ui={"sergio_h3_saved": [path]},
        )
