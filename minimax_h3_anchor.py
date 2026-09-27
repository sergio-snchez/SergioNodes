# coding: utf-8
"""
😺SergioNodes MiniMax H3 Chunk Anchor — conditioning de un chunk con continuidad opcional.

Este nodo hace tres cosas a la vez, que es lo que hace que la serie funcione:

  1. Calcula la geometría del chunk a partir de `duration_seconds`, snapping a la
     rejilla 17k+5 del modelo, y construye el AV latent vacío.

  2. Si el chunk anterior ya está guardado en el proyecto, le arranca los últimos
     `anchor_latent_frames` tokens latentes (y la cola de audio correspondiente) y
     los mete en el conditioning como `minimax_keyframes`. El DiT los reinserta en
     cada paso y **no los denoisea**, así que el chunk nuevo arranca literalmente
     desde donde terminó el anterior.

  3. Monta las referencias ref2va (imágenes / vídeos / audio) con el mismo contrato
     que el nodo nativo, de forma que ambos caben en un solo conditioning.

Sobre el punto 2, dos detalles que no son evidentes:

  - `resolved_frame_index` vale `frames(lf) - 1`, no `frames(lf)`. El último
    frame real del ancla es el que se solapa con el último frame del chunk
    anterior, y es el que el modelo tiene que tratar como ya establecido.
  - `anchor_latent_frames` **no puede ser 0**. Concatenar N clips nativos de la
    rejilla da 17*sum(k) + 5*N, que solo cae en la rejilla cuando N ≡ 1 (mod 17).
    Es decir que el solape es estructuralmente obligatorio en H3; el mínimo son
    2 tokens (5 frames) y no existe el "corte seco" en este modelo.
"""
from __future__ import annotations

UPSTREAM = None  # nodo original de SergioNodes (sin upstream; los nodos H3 nativos no guardan estado entre chunks)

import math
import time

import torch

import node_helpers
from comfy_api.latest import io

from . import h3_chunks as H

AUDIO_BED_LATENT_FRAMES = 80   # ~2 s a 40 Hz, para el modo "bed"
AUDIO_ANCHOR_MODES = ["trim", "bed", "off"]


def _native():
    """Import perezoso del módulo nativo de H3 para reusar sus helpers de referencia.

    Se reusan a propósito en vez de reimplementarlos: así las referencias de este
    nodo se comportan exactamente igual que las del nodo nativo. Si el módulo
    cambia de forma incompatible, preferimos un error claro a una divergencia
    silenciosa.
    """
    try:
        import comfy_extras.nodes_minimax_h3 as native
    except Exception as error:  # noqa: BLE001
        raise RuntimeError(
            "No se pudo importar comfy_extras.nodes_minimax_h3 ({}). Este nodo depende de los "
            "helpers de referencia de la versión de ComfyUI que incluye soporte de H3.".format(error)
        ) from error
    for attribute in ("_resize", "_encode_ref_audio", "adapt_canvas", "CANVAS_MULTIPLE",
                      "REF_IMAGE_SHORT_EDGE", "temporal_shape"):
        if not hasattr(native, attribute):
            raise RuntimeError(
                "comfy_extras.nodes_minimax_h3 ya no expone '{}'. La API de referencias de H3 "
                "cambió respecto a la versión para la que se escribió este nodo.".format(attribute))
    return native


def _any_connected(mapping) -> bool:
    """¿Hay algo realmente conectado en un grupo Autogrow?

    Ojo: los valores son tensores IMAGE/VIDEO/AUDIO, y `any()` les haría un `bool()`
    que revienta con "Boolean value of Tensor with more than one value is ambiguous".
    Aquí solo importa si la ranura está conectada, no su contenido.
    """
    if not mapping:
        return False
    if not isinstance(mapping, dict):
        return mapping is not None
    return any(value is not None for value in mapping.values())


def _build_refs(native, ref_image_size, vae, audio_vae, frame_count, width, height,
                ref_images, ref_videos, ref_video_audios, ref_audios):
    """Reproduce el contrato de referencias del nodo nativo (ref2va).

    Orden de presentación: imágenes, luego vídeos (con su banda sonora etiquetada
    justo antes) y por último audio suelto. Los ordinales son 1-based por tipo,
    así que el prompt los referencia como <Picture i> / <Video k> / <Audio j>.

    `width`/`height` son el lienzo efectivo ya resuelto por `execute`, y sirven para
    escalar la ref al área de generación ('match'). Cada bloque conserva su propia
    proporción y su propia rejilla latente.
    """
    multiple = native.CANVAS_MULTIPLE
    ref_items = []    # para la presentación del tokenizer, en orden de petición
    ref_blocks = []   # para el payload del DiT, mismo orden

    for image in (ref_images or {}).values():
        if image is None:
            continue
        # Las referencias llevan su propia rejilla: `PackedLayout` les da un cursor y un
        # `_frame_grid` propios, así que NO tienen que medir lo mismo que el target (el
        # nativo por eso admite 'max' a 2048 px contra un target de 1344). Lo que sí hace
        # falta es un múltiplo de 32 para que el VAE pueda trocearlas, y preservar la
        # proporción: estirar una cara en un ref de identidad se nota mucho.
        img_h, img_w = image.shape[1], image.shape[2]
        if ref_image_size == "match":
            scale = min(1.0, math.sqrt((width * height) / (img_w * img_h)))
        else:
            scale = min(1.0, native.REF_IMAGE_SHORT_EDGE / min(img_w, img_h))
        target_w = max(multiple, round(img_w * scale / multiple) * multiple)
        target_h = max(multiple, round(img_h * scale / multiple) * multiple)
        resized = native._resize(image[:1], target_w, target_h, "disabled")
        ref_items.append({"type": "image", "data": resized})
        if vae is not None:
            latent = vae.encode(resized)
            ref_blocks.append({"kind": "image", "latent_h": target_h // 16,
                               "latent_w": target_w // 16, "latent": latent})

    ref_video_audios = ref_video_audios or {}
    for name, video_frames in (ref_videos or {}).items():
        if video_frames is None:
            continue
        soundtrack = ref_video_audios.get("ref_video_audio_" + name.rsplit("_", 1)[-1])
        source_h, source_w = video_frames.shape[1], video_frames.shape[2]
        canvas_w, canvas_h = native.adapt_canvas(source_w, source_h)
        if source_w * source_h < canvas_w * canvas_h:
            canvas_w = max(multiple, round(source_w / multiple) * multiple)
            canvas_h = max(multiple, round(source_h / multiple) * multiple)
        frames = native._resize(video_frames, canvas_w, canvas_h, "disabled")
        if frames.shape[0] > frame_count:
            frames = frames[:frame_count]
        count = frames.shape[0]
        if count < 5:
            raise ValueError("Los vídeos de referencia de MiniMax H3 necesitan al menos 5 frames (~0.2s a 24 fps)")
        while count % 17 != 5:
            count -= 1
        frames = frames[:count]
        if soundtrack is not None:
            ref_items.append({"type": "audio"})
        sample_idx = list(range(0, frames.shape[0], H.FPS // 2))
        ref_items.append({"type": "video", "data": frames[sample_idx],
                          "timestamps": [i / 2.0 for i in range(len(sample_idx))]})
        if vae is None:
            continue
        latent = vae.encode(frames)
        audio_latent, ref_audio_t = (None, 0)
        if soundtrack is not None and audio_vae is not None:
            audio_latent, ref_audio_t = native._encode_ref_audio(audio_vae, soundtrack)
        ref_blocks.append({"kind": "video_audio" if ref_audio_t else "video",
                           "latent_t": latent.shape[2], "latent_h": canvas_h // 16,
                           "latent_w": canvas_w // 16, "ref_audio_t": ref_audio_t,
                           "latent": latent, "audio_latent": audio_latent})

    for audio in (ref_audios or {}).values():
        if audio is None:
            continue
        ref_items.append({"type": "audio"})
        if audio_vae is not None:
            audio_latent, ref_audio_t = native._encode_ref_audio(audio_vae, audio)
            ref_blocks.append({"kind": "audio", "ref_audio_t": ref_audio_t, "audio_latent": audio_latent})

    return ref_items, ref_blocks


H3_PATCH_SIZE = (1, 2, 2)


def _video_tensor(latent):
    """Saca el tensor de vídeo de un latent AV de H3.

    `native._empty_av_latent` devuelve `{"samples": NestedTensor((video, audio))}`, o sea
    un dict, no un tensor. El vídeo es el primero de los dos.
    """
    samples = latent["samples"] if isinstance(latent, dict) else latent
    if getattr(samples, "is_nested", False):
        return samples.tensors[0]
    return samples


def _pad_to_patch(latent):
    """Rellena el latent hasta múltiplo del parche, igual que hace el DiT con el suyo.

    El nativo rellena el latent principal con `pad_to_patch_size` (mode="circular") y
    luego recorta al deshacer el patchify, así que un latent de anchura impar es
    perfectly válido para generar. Pero el keyframe entra por otra puerta: `_cond_video_rows`
    llama a `patchify_video` sin rellenar, y ahí `85 // 2 == 42` deja 84 columnas de 85 y el
    reshape revienta con "shape [...] is invalid for input of size ...". Por eso el keyframe
    necesita el mismo relleno que el video latent.
    """
    pad_h = (H3_PATCH_SIZE[1] - int(latent.shape[3]) % H3_PATCH_SIZE[1]) % H3_PATCH_SIZE[1]
    pad_w = (H3_PATCH_SIZE[2] - int(latent.shape[4]) % H3_PATCH_SIZE[2]) % H3_PATCH_SIZE[2]
    if not pad_h and not pad_w:
        return latent
    # [B, C, T, H, W] -> hay que rellenar las tres últimas dims, no solo dos.
    return torch.nn.functional.pad(latent, (0, pad_w, 0, pad_h, 0, 0), mode="circular")


def _resolve_canvas(native, requested_w, requested_h, previous, index):
    """Decide el lienzo efectivo de un chunk y explica cualquier override.

    El keyframe de un chunk encadenado es la cola del chunk anterior, así que ambos
    latents tienen que compartir la MISMA rejilla espacial. Si no, el DiT recibe un
    tensor que no encaja y revienta con un reshape incomprensible
    ("shape [...] is invalid for input of size ..."). Al encadenar manda el chunk
    previo aunque el widget diga otra cosa; el chunk 1 usa el ``adapt_canvas`` del
    nativo, que recorta al área máxima y deja el lienzo en un múltiplo de 32.
    """
    notes = []
    requested_w, requested_h = int(requested_w), int(requested_h)
    if previous is not None and previous.get("width") and previous.get("height"):
        canvas_w, canvas_h = int(previous["width"]), int(previous["height"])
        if (canvas_w, canvas_h) != (requested_w, requested_h):
            notes.append("Lienzo pedido {}x{} -> {}x{}: manda el chunk {}, porque su cola "
                         "es el keyframe y ambos deben compartir lienzo.".format(
                             requested_w, requested_h, canvas_w, canvas_h, int(index) - 1))
    else:
        canvas_w, canvas_h = native.adapt_canvas(requested_w, requested_h)
        if (canvas_w, canvas_h) != (requested_w, requested_h):
            notes.append("Lienzo pedido {}x{} -> {}x{} (adapt_canvas del nativo).".format(
                requested_w, requested_h, canvas_w, canvas_h))

    if canvas_w % 16 or canvas_h % 16:
        raise ValueError("Lienzo {}x{} no es múltiplo de 16, el VAE no lo puede trocear. "
                         "Pide un ancho múltiplo de 32.".format(canvas_w, canvas_h))
    if canvas_w % 32 or canvas_h % 32:
        notes.append("Lienzo {}x{} no es múltiplo de 32: el latent sale con dimensión impar y el "
                     "DiT tiene que inventar una columna de relleno (padding circular) en el "
                     "borde derecho. Funciona, pero es territorio fuera de la rejilla de H3; "
                     "1344x768 es el lienzo canónico.".format(canvas_w, canvas_h))
    return canvas_w, canvas_h, notes


class MinimaxH3ChunkAnchor(io.ComfyNode):
    """Build one chunk's conditioning, optionally anchored to the previous chunk's tail."""

    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="MinimaxH3ChunkAnchor",
            display_name="Minimax H3 Chunk Anchor",
            category="Sergio Nodes",
            search_aliases=[
                "h3 chunk anchor",
                "h3 anchor",
                "h3 continuity",
                "ancla h3",
                "continuidad h3",
            ],
            description=(
                "Builds the AV latent and conditioning for one chunk of a long MiniMax H3 video. "
                "When the previous chunk exists in the project, its last latent frames are injected "
                "as a keyframe anchor that is never denoised, so the new chunk starts where the "
                "previous one ended. Optional ref2va references ride in the same conditioning."
            ),
            inputs=[
                io.String.Input("project", default="h3_project", multiline=False,
                                tooltip="Project handle coming from Minimax H3 Project."),
                io.Int.Input("chunk_index", default=1, min=1, max=9999,
                             tooltip="Which chunk this is. Chunk 1 has no anchor; from chunk 2 on, the "
                                     "previous chunk stored in the project is used as the anchor."),
                io.Clip.Input("clip", tooltip="The MiniMax H3 text encoder (Qwen3-VL based)."),
                io.String.Input("prompt", multiline=True, dynamic_prompts=True,
                                tooltip="Prompt for THIS chunk only. Write the continuity you want here."),
                io.Float.Input("duration_seconds", default=5.0, min=0.21, max=150.0, step=0.1,
                               tooltip="Requested chunk duration. Snapped UP to the model's 17k+5 frame "
                                       "grid at 24 fps, so 5.0s becomes 124 frames (5.17s)."),
                io.Int.Input("width", default=1344, min=32, max=16384, step=32,
                             tooltip="Target width. From chunk 2 on this is IGNORED in favour of the "
                                     "previous chunk's canvas, because that chunk's tail becomes the "
                                     "keyframe anchor and both must share the exact same latent grid."),
                io.Int.Input("height", default=768, min=32, max=16384, step=32,
                             tooltip="Target height. Same rule as width: the previous chunk's canvas "
                                     "wins once you are chaining."),
                io.Int.Input("anchor_latent_frames", default=2, min=2, max=12,
                             tooltip="How many latent frames of the previous chunk to replay. 2 = minimal "
                                     "(5 real frames, least duplication), 7 = stronger continuity, 12 = "
                                     "strongest. MUST be 2 or more: H3's grid makes overlap mandatory, so "
                                     "a hard cut does not exist. The chunk also has to be long enough to "
                                     "absorb it."),
                io.Combo.Input("audio_anchor_mode", options=AUDIO_ANCHOR_MODES, default="trim",
                               tooltip="How much previous audio to condition on. 'trim' = only the overlap "
                                       "tail, 'bed' = up to ~2s of previous audio so ambience and timbre "
                                       "carry over, 'off' = video continuity only."),
                io.Vae.Input("vae", optional=True,
                             tooltip="Video VAE. Optional: only needed if you connect reference images/videos."),
                io.Vae.Input("audio_vae", optional=True,
                             tooltip="Audio VAE. Only needed if you connect reference audio or first/last frames."),
                io.Combo.Input("ref_image_size", options=["match", "max"], default="match",
                               tooltip="Reference image sizing. 'match' scales each ref down to the "
                                       "generation's pixel area; 'max' uses a 2048px short edge for best "
                                       "identity fidelity, but reference tokens ride through every step, "
                                       "so it can be several times slower. Either way each ref keeps its "
                                       "own aspect ratio and its own latent grid, so it does not have to "
                                       "match the target size."),
                io.Autogrow.Input("ref_images", optional=True,
                                  template=io.Autogrow.TemplatePrefix(
                                      input=io.Image.Input("ref_image"),
                                      prefix="ref_image_", min=0, max=9)),
                io.Autogrow.Input("ref_videos", optional=True,
                                  template=io.Autogrow.TemplatePrefix(
                                      input=io.Image.Input("ref_video",
                                                           tooltip="Reference video frames at 24 fps (2-15s)"),
                                      prefix="ref_video_", min=0, max=3)),
                io.Autogrow.Input("ref_video_audios", optional=True,
                                  template=io.Autogrow.TemplatePrefix(
                                      input=io.Audio.Input("ref_video_audio",
                                                           tooltip="Soundtrack of the same-numbered reference video"),
                                      prefix="ref_video_audio_", min=0, max=3)),
                io.Autogrow.Input("ref_audios", optional=True,
                                  template=io.Autogrow.TemplatePrefix(
                                      input=io.Audio.Input("ref_audio"),
                                      prefix="ref_audio_", min=0, max=3)),
            ],
            outputs=[
                io.Conditioning.Output(display_name="positive", tooltip="Feed to a KSampler."),
                io.Latent.Output(display_name="LATENT", tooltip="Feed to a KSampler."),
                io.Int.Output("frames_back", tooltip="How many real frames back the anchor keyframe is pinned."),
                io.String.Output("report", tooltip="What this node decided and why."),
            ],
        )

    @classmethod
    def execute(cls, project, chunk_index, clip, prompt, duration_seconds, width, height,
                anchor_latent_frames=2, audio_anchor_mode="trim", vae=None, audio_vae=None,
                ref_image_size="match", ref_images=None, ref_videos=None,
                ref_video_audios=None, ref_audios=None) -> io.NodeOutput:
        native = _native()
        notes = []

        # --- 1. geometría del chunk -------------------------------------------
        frames = H.seconds_to_frames(duration_seconds)
        snapped = H.frames_to_seconds(frames)
        if abs(snapped - float(duration_seconds)) > 1e-6:
            notes.append("Duración {}s -> {} frames ({:.2f}s) por la rejilla 17k+5.".format(
                duration_seconds, frames, snapped))
        latent_t = H.latent_t_for_frames(frames)
        audio_t = H.audio_t_for_frames(frames)

        # --- 2. ancla desde el chunk anterior ---------------------------------
        index = int(chunk_index)
        anchor_tokens = H.normalize_anchor_latent_frames(anchor_latent_frames)
        directory = H.project_dir(project)
        data = H.read_index(directory)
        previous = H.index_entry(data, index - 1) if index > 1 else None

        canvas_w, canvas_h, canvas_notes = _resolve_canvas(
            native, int(width), int(height), previous, index)
        notes.extend(canvas_notes)

        latent, native_frames = native._empty_av_latent(canvas_w, canvas_h, frames)
        if int(native_frames) != frames:
            raise RuntimeError("Discrepancia de rejilla: el nativo devolvió {} frames, aquí {}".format(
                native_frames, frames))

        keyframes = []
        frames_back = 0
        anchor_audio = None
        anchor_note = "sin ancla"

        if previous is not None:
            previous_frames = int(previous.get("frames", 0))
            previous_latent_t = H.latent_t_for_frames(previous_frames)
            if anchor_tokens > previous_latent_t:
                raise ValueError(
                    "El chunk {} tiene {} tokens latentes y no puede dar {} tokens de ancla. "
                    "Baja anchor_latent_frames a {} o alarga ese chunk.".format(
                        index - 1, previous_latent_t, anchor_tokens, H.normalize_anchor_latent_frames(previous_latent_t)))
            if not H.anchor_is_feasible(anchor_tokens, frames):
                raise ValueError(
                    "Este chunk pide {}s ({} tokens) y no puede absorber un ancla de {} tokens: "
                    "se quedaría con {} tokens. Baja anchor_latent_frames a {} o pide al menos {}s ({} frames).".format(
                        duration_seconds, latent_t, anchor_tokens, latent_t - anchor_tokens,
                        H.normalize_anchor_latent_frames(latent_t - H.LATENT_HEAD),
                        H.frames_to_seconds(H.min_frames_for_anchor(anchor_tokens)),
                        H.min_frames_for_anchor(anchor_tokens)))

            previous_video, previous_audio = H.load_chunk(directory, index - 1)
            target_video = _video_tensor(latent)
            if tuple(previous_video.shape[3:]) != tuple(target_video.shape[3:]):
                raise ValueError(
                    "El chunk {} se guardó con un latent de {} y este pide {}. La cola de "
                    "aquel es el keyframe de este, así que el lienzo tiene que ser idéntico. "
                    "O regenera el chunk {} a {}x{}, o reinicia el proyecto.".format(
                        index - 1, tuple(previous_video.shape[3:]), tuple(target_video.shape[3:]),
                        index - 1, canvas_w, canvas_h))
            frames_back = H.frames_back_for_anchor(anchor_tokens)
            tail_video = previous_video[:, :, -anchor_tokens:].contiguous()
            padded_tail = _pad_to_patch(tail_video)
            if padded_tail.shape != tail_video.shape:
                notes.append("Keyframe rellenado de {}x{} a {}x{} para cuadrar con el parche "
                             "2x2 del DiT.".format(
                                 int(tail_video.shape[4]), int(tail_video.shape[3]),
                                 int(padded_tail.shape[4]), int(padded_tail.shape[3])))
            keyframe = {"resolved_frame_index": frames_back, "latent": padded_tail}

            if audio_anchor_mode != "off":
                overlap_frames = H.frames_for_latent_t(anchor_tokens)
                if audio_anchor_mode == "bed":
                    wanted = AUDIO_BED_LATENT_FRAMES
                else:
                    wanted = H.frames_to_audio_t_offset(overlap_frames)
                tail_audio = previous_audio[..., -min(wanted, int(previous_audio.shape[-1])):].contiguous()
                # misma regla que el nodo nativo: el audio no puede pasar del final del clip
                capacity = int(math.floor(audio_t - H.AUDIO_RESCALE * frames_back))
                if capacity < 1:
                    notes.append("El ancla de audio no cabe ({} frames de audio restantes); se omite.".format(capacity))
                else:
                    if int(tail_audio.shape[-1]) > capacity:
                        tail_audio = tail_audio[..., :capacity].contiguous()
                        notes.append("Audio ancla recortado a {} frames latentes por capacidad del clip.".format(capacity))
                    keyframe["audio_latent"] = tail_audio
                    anchor_audio = int(tail_audio.shape[-1])
            else:
                notes.append("Continuidad de audio desactivada (audio_anchor_mode = off).")

            keyframes.append(keyframe)
            anchor_note = ("anclado al chunk {} ({} tokens = {} frames reales, frames_back={}, "
                           "audio={} tokens)").format(index - 1, anchor_tokens,
                                                      H.frames_for_latent_t(anchor_tokens),
                                                      frames_back, anchor_audio)
        elif index > 1:
            notes.append("El chunk {} todavía no está guardado: este chunk se generará SIN ancla. "
                         "Genera y guarda el chunk {} primero.".format(index - 1, index - 1))
        else:
            notes.append("Chunk 1: arranca la línea de tiempo, sin ancla (correcto).")

        # --- 3. referencias ref2va --------------------------------------------
        ref_items, ref_blocks = [], []
        if _any_connected(ref_images) or _any_connected(ref_videos) or _any_connected(ref_audios):
            ref_items, ref_blocks = _build_refs(
                native, ref_image_size, vae, audio_vae, frames, canvas_w, canvas_h,
                ref_images, ref_videos, ref_video_audios, ref_audios)
            notes.append("Referencias: {} imágenes, {} vídeos, {} bloques para el DiT.".format(
                sum(1 for item in ref_items if item["type"] == "image"),
                sum(1 for item in ref_items if item["type"] == "video"),
                len(ref_blocks)))
            notes.append("Usa el checkpoint ref2va si conectas referencias; con fl2va se ignoran.")

        if ref_items:
            tokens = clip.tokenize(prompt, minimax_ref_items=ref_items)
        else:
            tokens = clip.tokenize(prompt)
        conditioning = clip.encode_from_tokens_scheduled(tokens)

        if ref_blocks:
            conditioning = node_helpers.conditioning_set_values(conditioning, {"minimax_refs": ref_blocks})
        if keyframes:
            conditioning = node_helpers.conditioning_set_values(conditioning, {"minimax_keyframes": keyframes})

        # --- 4. registrar la política para que el Vault no tenga que adivinar ---
        data["pending"] = {
            "index": index,
            "requested_seconds": float(duration_seconds),
            "anchor_latent_frames": anchor_tokens if previous is not None else 0,
            "anchor_frames_back": frames_back,
            "anchor_audio_latent_t": anchor_audio,
            "audio_anchor_mode": audio_anchor_mode,
            "width": int(canvas_w),
            "height": int(canvas_h),
            "prompt": (prompt or "")[:400],
            "has_refs": bool(ref_blocks),
            "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        H.write_index(directory, data)

        report = "\n".join([
            "Chunk {} | proyecto {}".format(index, data.get("name", project)),
            "Geometría: {}x{}, {} frames, latent_t={}, audio_t={}".format(
                canvas_w, canvas_h, frames, latent_t, audio_t),
            "Continuidad: {}".format(anchor_note),
        ] + notes)

        return io.NodeOutput(conditioning, latent, frames_back, report,
                             ui={"sergio_h3_chunk": [str(index)]})
