# coding: utf-8
"""
SergioNodes — Motor de chunks para MiniMax H3 (aritmética de latentes y almacenamiento).

Este módulo no es un nodo: es la capa que los nodos de la serie H3 Long Video
comparten. Concentra todo lo que es fácil equivocarse.

Por qué existe un motor propio
------------------------------
El latente AV de MiniMax H3 **no es un tensor homogéneo en el tiempo**:

    latent["samples"] = NestedTensor( video [1,24,T,H/16,W/16],
                                      audio [1,32,2,Ta] )

y la compresión temporal del VAE de vídeo es f16t4d24 con

    FRAME_PER_TOKEN = (1, 4, 4, 4, 4)

Es decir: el primer frame latente codifica **1** frame real y los cuatro
siguientes codifican **4** cada uno, en ciclo. De ahí se derivan las dos
invariantes que gobiernan todo el sistema:

  1. Rejilla de frames:  F = 17k + 5        (frames reales de un clip válido)
     Equivalente:        T = 5k + 2         (frames latentes de un clip válido)
     `latent_t % 5 == 2` es la condición de validez del DiT.

  2. Audio:              Ta = round(F * 5/3)  (40 Hz de latente sobre 24 fps)

Un `torch.cat` ingenuo entre dos clips de 124 frames produce 248 frames, que
es 248 % 17 == 10 → forma inválida, y además rompe la fase de FRAME_PER_TOKEN
en la costura. Este módulo es lo que evita eso.

La regla de fusión
------------------
Un ancla de `lf` frames latentes hace que el chunk N **reproduzca** a
propósito los últimos frames del chunk N-1. La fusión debe eliminar esa
duplicación, y para que la fase siga siendo legal hace falta `lf ≡ 2 (mod 5)`:

    fusión = chunk_1[0:L]  ++  chunk_i[lf:L]   para i > 1

Los frames reales resultantes son

    F_merged = 17 * ( sum(k_i) + m*(N-1) ) + 5     con lf = 5m + 2

es decir, **exactamente los mismos blocks que un clip nativo de esa duración**,
con la misma línea de tiempo RoPE (`_video_t_grid` genera la rejilla por
fórmula para cualquier T). Ésa es la razón de que la fusión sea limpia: el
modelo nunca ve un eje temporal que no haya visto.

"""
from __future__ import annotations

UPSTREAM = None  # motor interno original de SergioNodes (capa compartida de H3 Long Video)

import json
import os
import re
import time

import torch

import comfy.utils
import folder_paths
from comfy.nested_tensor import NestedTensor

# ==========================================
# Constantes del modelo (comfy/ldm/minimax/model.py)
# ==========================================
FPS = 24
AUDIO_LATENT_FPS = 40
AUDIO_RESCALE = AUDIO_LATENT_FPS / FPS          # 5/3 == FRAME_RESCALE
VIDEO_CHANNELS = 24
AUDIO_CHANNELS = 32
AUDIO_STREAMS = 2
VAE_SPATIAL_DOWNSCALE = 16
FRAME_PER_TOKEN = (1, 4, 4, 4, 4)

# frames() de 5q + r, para r = 0..5
_FRAMES_PARTIAL = (0, 1, 5, 9, 13, 17)
CHUNK_BLOCK = 17        # frames reales por block temporal
CHUNK_HEAD = 5          # el primer block son 5 frames, luego +17 cada uno
LATENT_BLOCK = 5        # frames latentes por block
LATENT_HEAD = 2         # el primer block son 2 frames latentes, luego +5

PROJECT_DIRNAME = "h3_projects"
INDEX_FILENAME = "project.json"
CHUNK_TEMPLATE = "chunk_{:04d}.safetensors"
PROJECT_NAME_MAX = 64
_PROJECT_NAME_SAFE = re.compile(r"[^A-Za-z0-9 _-]+")


# ==========================================
# Aritmética temporal
# ==========================================
def frames_for_latent_t(latent_t: int) -> int:
    """Frames reales que cubren `latent_t` frames latentes bajo FRAME_PER_TOKEN."""
    latent_t = int(latent_t)
    if latent_t < 1:
        raise ValueError("latent_t debe ser >= 1, recibido {}".format(latent_t))
    blocks, rest = divmod(latent_t, LATENT_BLOCK)
    return CHUNK_BLOCK * blocks + _FRAMES_PARTIAL[rest]


def latent_t_for_frames(frames: int) -> int:
    """Frames latentes de un clip nativo de `frames` frames (inversa de la anterior)."""
    frames = int(frames)
    if frames <= CHUNK_HEAD:
        return LATENT_HEAD
    return ((frames - CHUNK_HEAD) // CHUNK_BLOCK) * LATENT_BLOCK + LATENT_HEAD


def align_frame_count(frames: int) -> int:
    """Sube `frames` al siguiente valor de la rejilla 17k+5 (mismo criterio que el nodo nativo)."""
    frames = max(int(frames), CHUNK_HEAD)
    blocks = -(-(frames - CHUNK_HEAD) // CHUNK_BLOCK)   # ceil sin float
    return CHUNK_HEAD + CHUNK_BLOCK * blocks


def seconds_to_frames(seconds: float) -> int:
    """Segundos -> frames en la rejilla 17k+5."""
    return align_frame_count(int(round(float(seconds) * FPS)))


def frames_to_seconds(frames: int) -> float:
    return float(frames) / FPS


def audio_t_for_frames(frames: int) -> int:
    """Frames de latente de audio (40 Hz) para `frames` frames reales a 24 fps."""
    return int(round(int(frames) * AUDIO_RESCALE))


def frames_to_audio_t_offset(frames: int) -> int:
    """Offset de audio correspondiente a `frames` frames reales de scrolling."""
    return int(round(int(frames) * AUDIO_RESCALE))


def is_valid_latent_t(latent_t: int) -> bool:
    latent_t = int(latent_t)
    return latent_t >= LATENT_HEAD and (latent_t - LATENT_HEAD) % LATENT_BLOCK == 0


def is_valid_anchor_latent_frames(latent_frames: int) -> bool:
    """El ancla debe consumir un número de frames latentes ≡ 2 (mod 5) para que la fase case."""
    latent_frames = int(latent_frames)
    return latent_frames >= LATENT_HEAD and (latent_frames - LATENT_HEAD) % LATENT_BLOCK == 0


def frames_back_for_anchor(latent_frames: int) -> int:
    """Frame real al que hay que anclar el keyframe para que la fase del nuevo clip alinee.

    El keyframe ocupa los primeros `latent_frames` tokens del clip nuevo, y su
    contenido es la cola del chunk anterior. Measured (Moviola): el frame 4 del
    clip nuevo es el que reproduce el último frame del anterior, o sea que el
    ancla tiene que situarse `frames(lf) - 1` frames antes del final.
    """
    return frames_for_latent_t(latent_frames) - 1


def normalize_anchor_latent_frames(latent_frames: int, default: int = 2) -> int:
    """Normaliza el número de frames latentes del ancla al valor válido más cercano.

    OJO, y esto no es una decisión de diseño sino una consecuencia de la rejilla:
    **no existe el corte seco**. Concatenar N clips nativos da 17*sum(k)+5*N, que
    solo cae en la rejilla 17k+5 cuando N ≡ 1 (mod 17), es decir para N = 1, 18,
    35... Es decir, inútil. Por tanto toda unión tiene que solapar, y el solape
    mínimo son 2 tokens (5 frames reales). Un valor <= 0 se sube a 2.
    """
    latent_frames = int(latent_frames)
    if latent_frames < LATENT_HEAD:
        return LATENT_HEAD
    blocks = -(-(latent_frames - LATENT_HEAD) // LATENT_BLOCK)
    return LATENT_HEAD + LATENT_BLOCK * blocks


def max_anchor_latent_frames(frames: int) -> int:
    """Mayor ancla que un chunk de `frames` puede absorber sin quedarse vacío.

    Sin suelo artificial: si el chunk tiene menos de 2*LATENT_HEAD tokens no puede
    absorber ninguna ancla, porque se quedaría sin contenido que aportar. Un chunk de
    5 frames (latent_t 2) no vale como chunk 2 con ancla 2, aunque 'cabe' exactamente.
    """
    return max(latent_t_for_frames(frames) - LATENT_HEAD, 0)


def anchor_is_feasible(anchor_latent_frames: int, frames: int) -> bool:
    """El chunk tiene que ser capaz de absorber el solape conservando >= 2 tokens."""
    return normalize_anchor_latent_frames(anchor_latent_frames) <= max_anchor_latent_frames(frames)


def min_frames_for_anchor(anchor_latent_frames: int) -> int:
    """Duración mínima de un chunk que puede absorber ese ancla.

    El chunk receptor también tiene que estar en la rejilla, así que su latent_t
    tiene que ser ≡ 2 (mod 5). El menor valor válido que supera al ancla es
    ancla + 5 tokens, no ancla + 2: con ancla 2 el mínimo es latent_t 7, o sea
    22 frames, no 13.
    """
    return frames_for_latent_t(normalize_anchor_latent_frames(anchor_latent_frames) + LATENT_BLOCK)


def merge_block_count(chunk_blocks, entry_anchors) -> int:
    """Blocks de 17 frames del latente fusionado, dados los blocks de cada chunk.

    Descartar `lf = 5m+2` tokens del frente de un chunk elimina
    `frames(lf) = 17m+5` frames reales, o sea m blocks completos **más** la
    cabeza de 5 frames que ya no puede darse por válida por sí sola. Por eso el
    total de blocks *baja* en m por cada unión:

        blocks_fusionados = sum(k_i) - m*(N-1)
        frames_fusionados = 17 * blocks_fusionados + 5

    Comprobación: 3 chunks de 124 frames (k=7) con ancla 7 (m=1) ->
    21 - 2 = 19 blocks -> 17*19+5 = 328 frames, que es 124*3 - 22*2. ✓
    """
    total = int(sum(chunk_blocks))
    for anchor in list(entry_anchors)[1:]:
        if int(anchor) > 0:
            total -= (int(anchor) - LATENT_HEAD) // LATENT_BLOCK
    return max(total, 0)


# ==========================================
# Latentes AV
# ==========================================
def is_h3_av_latent(latent) -> bool:
    samples = latent.get("samples") if isinstance(latent, dict) else None
    if samples is None or not getattr(samples, "is_nested", False):
        return False
    tensors = samples.unbind()
    return len(tensors) == 2 and tensors[0].dim() == 5 and int(tensors[0].shape[1]) == VIDEO_CHANNELS


def require_h3_av_latent(latent, who: str):
    if not isinstance(latent, dict) or "samples" not in latent:
        raise ValueError("{}: se esperaba un LATENT.".format(who))
    samples = latent["samples"]
    if not getattr(samples, "is_nested", False) or len(samples.unbind()) != 2:
        raise ValueError(
            "{}: el latente no es un AV latent anidado de MiniMax H3 (video + audio). "
            "Usa uno de los nodos nativos de H3 para crear el latent.".format(who))
    video, audio = samples.unbind()
    if video.dim() != 5 or int(video.shape[1]) != VIDEO_CHANNELS:
        raise ValueError("{}: el stream de vídeo debería ser [B,{},T,H,W], recibido {}".format(
            who, VIDEO_CHANNELS, tuple(video.shape)))
    if audio.dim() != 4 or int(audio.shape[1]) != AUDIO_CHANNELS or int(audio.shape[2]) != AUDIO_STREAMS:
        raise ValueError("{}: el stream de audio debería ser [B,{},{},T], recibido {}".format(
            who, AUDIO_CHANNELS, AUDIO_STREAMS, tuple(audio.shape)))
    if int(video.shape[0]) != 1:
        raise ValueError("{}: H3 solo admite batch size 1, recibido {}".format(who, int(video.shape[0])))
    return video, audio


def build_av_latent(video: torch.Tensor, audio: torch.Tensor) -> dict:
    return {"samples": NestedTensor((video, audio))}


def video_geometry(video: torch.Tensor) -> dict:
    latent_t = int(video.shape[2])
    return {
        "latent_t": latent_t,
        "frames": frames_for_latent_t(latent_t),
        "latent_h": int(video.shape[3]),
        "latent_w": int(video.shape[4]),
        "height": int(video.shape[3]) * VAE_SPATIAL_DOWNSCALE,
        "width": int(video.shape[4]) * VAE_SPATIAL_DOWNSCALE,
        "valid_grid": is_valid_latent_t(latent_t),
    }


def check_same_canvas(videos, who: str) -> tuple:
    """Comprueba que todos los chunks comparten geometría y devuelve (latent_h, latent_w)."""
    shapes = {tuple(v.shape[-2:]) for v in videos}
    if len(shapes) != 1:
        raise ValueError("{}: los chunks tienen resoluciones distintas: {}".format(
            who, sorted(shapes)))
    return next(iter(shapes))


def drop_leading_latent_frames(video: torch.Tensor, audio: torch.Tensor, latent_frames: int,
                               audio_drop: int):
    """Quita `latent_frames` frames latentes por delante y `audio_drop` frames de audio.

    Se usa en dos sitios con la misma idea:
      - fusión de chunks: el ancla hizo que el chunk nuevo repita la cola del
        anterior, y esa repetición se elimina aquí.
      - recorte de un chunk suelto.
    """
    if latent_frames > 0:
        video = video[:, :, latent_frames:].contiguous()
    if audio_drop > 0:
        audio = audio[..., audio_drop:].contiguous()
    return video, audio


def trim_or_pad_audio(audio: torch.Tensor, target_t: int) -> torch.Tensor:
    """Fuerza el stream de audio a `target_t` frames, sin dejar que la deriva de redondeo se acumule."""
    have = int(audio.shape[-1])
    if have == target_t:
        return audio
    if have > target_t:
        return audio[..., :target_t].contiguous()
    pad = target_t - have
    return torch.cat([audio, audio[..., -1:].expand(-1, -1, -1, pad)], dim=-1).contiguous()


# ==========================================
# Rutas de proyecto
# ==========================================
def sanitize_project_name(name: str) -> str:
    """Filtra el nombre por allow-list: acaba en una ruta de disco."""
    cleaned = _PROJECT_NAME_SAFE.sub("", str(name or "")).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned:
        raise ValueError("El nombre del proyecto está vacío tras sanear.")
    return cleaned[:PROJECT_NAME_MAX]


def projects_root() -> str:
    return os.path.join(folder_paths.get_output_directory(), PROJECT_DIRNAME)


def project_dir(name: str, create: bool = True) -> str:
    safe = sanitize_project_name(name)
    root = os.path.abspath(projects_root())
    target = os.path.abspath(os.path.join(root, safe))
    # containment check con startswith y no con commonpath: commonpath lanza
    # ValueError si las rutas caen en unidades distintas, y una excepcion aqui
    # seria menos util que un rechazo claro.
    if not target.startswith(root.rstrip(os.sep) + os.sep):
        raise ValueError("La ruta del proyecto se sale del directorio permitido: {}".format(name))
    if create:
        os.makedirs(target, exist_ok=True)
    return target


def list_projects() -> list:
    root = projects_root()
    if not os.path.isdir(root):
        return []
    return sorted(name for name in os.listdir(root)
                  if os.path.isfile(os.path.join(root, name, INDEX_FILENAME)))


def chunk_path(directory: str, index: int) -> str:
    return os.path.join(directory, CHUNK_TEMPLATE.format(int(index)))


def index_path(directory: str) -> str:
    return os.path.join(directory, INDEX_FILENAME)


# ==========================================
# Índice del proyecto
# ==========================================
def blank_index(name: str) -> dict:
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
    return {"name": name, "created": stamp, "updated": stamp, "fps": FPS,
            "project": "H3 Long Video / SergioNodes", "chunks": [], "pending": None}


def read_index(directory: str) -> dict:
    path = index_path(directory)
    if not os.path.isfile(path):
        return blank_index(os.path.basename(directory))
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as error:
        raise ValueError("No se pudo leer el índice del proyecto {}: {}".format(path, error)) from error
    data.setdefault("chunks", [])
    data.setdefault("pending", None)
    data.setdefault("fps", FPS)
    return data


def write_index(directory: str, data: dict) -> str:
    data["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    path = index_path(directory)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
    os.replace(tmp, path)
    return path


def index_entry(data: dict, index: int):
    for entry in data.get("chunks", []):
        if int(entry.get("index", -1)) == int(index):
            return entry
    return None


def upsert_entry(data: dict, entry: dict) -> None:
    chunks = data.setdefault("chunks", [])
    for position, existing in enumerate(chunks):
        if int(existing.get("index", -1)) == int(entry["index"]):
            chunks[position] = entry
            break
    else:
        chunks.append(entry)
    chunks.sort(key=lambda item: int(item.get("index", 0)))


def next_free_index(data: dict) -> int:
    used = {int(entry.get("index", 0)) for entry in data.get("chunks", [])}
    index = 1
    while index in used:
        index += 1
    return index


def existing_indexes(data: dict) -> list:
    return sorted(int(entry.get("index", 0)) for entry in data.get("chunks", []))


def select_chunks(data: dict, first_index: int, last_index: int) -> list:
    """Chunks contiguos del rango pedido, saltando los huecos con un aviso en vez de fallar."""
    available = existing_indexes(data)
    if not available:
        raise ValueError("El proyecto no tiene chunks guardados todavía.")
    low, high = min(first_index, last_index), max(first_index, last_index)
    chosen = [i for i in available if low <= i <= high]
    if not chosen:
        raise ValueError("No hay chunks en el rango {}-{} (disponibles: {}).".format(
            low, high, available))
    return chosen


# ==========================================
# IO de chunks
# ==========================================
def save_chunk(directory: str, index: int, video: torch.Tensor, audio: torch.Tensor,
               metadata: dict) -> tuple:
    """Guarda un chunk como safetensors plano (video/audio) y devuelve (ruta, bytes)."""
    import safetensors.torch

    path = chunk_path(directory, index)
    tensors = {
        "video": video.detach().to("cpu").contiguous(),
        "audio": audio.detach().to("cpu").contiguous(),
    }
    meta = {key: str(value) for key, value in metadata.items()}
    comfy.utils.save_torch_file(tensors, path, metadata=meta)
    return path, os.path.getsize(path)


def load_chunk(directory: str, index: int) -> tuple:
    import safetensors.torch

    path = chunk_path(directory, index)
    if not os.path.isfile(path):
        raise FileNotFoundError("No existe el chunk {}: {}".format(index, path))
    tensors = safetensors.torch.load_file(path, device="cpu")
    if "video" not in tensors or "audio" not in tensors:
        raise ValueError("El chunk {} no tiene los streams video/audio esperados.".format(index))
    return tensors["video"].float(), tensors["audio"].float()


def load_chunk_entry(directory: str, entry: dict) -> tuple:
    """Carga respetando el nombre de fichero registrado en el índice."""
    path = chunk_path(directory, int(entry["index"]))
    if not os.path.isfile(path):
        raise FileNotFoundError("El índice apunta a un chunk inexistente: {}".format(path))
    return load_chunk(directory, int(entry["index"]))


def delete_chunk(directory: str, index: int) -> bool:
    path = chunk_path(directory, index)
    removed = os.path.isfile(path) and os.remove(path)
    data = read_index(directory)
    data["chunks"] = [e for e in data.get("chunks", []) if int(e.get("index", -1)) != int(index)]
    write_index(directory, data)
    return removed


def project_bytes(data: dict) -> int:
    return sum(int(entry.get("bytes", 0)) for entry in data.get("chunks", []))


# ==========================================
# Fusión
# ==========================================
def plan_merge(entries: list, anchor_override=None) -> dict:
    """Calcula los cortes de vídeo y audio de la fusión sin tocar tensores.

    `entries` son las entradas del índice, en orden. `anchor_override` permite
    forzar un número de frames latentes de ancla para todos los chunks salvo el
    primero; por defecto se usa el que cada chunk grabó al generarse.
    """
    if not entries:
        raise ValueError("No hay chunks que fusionar.")

    anchors = []
    for entry in entries:
        recorded = int(entry.get("anchor_latent_frames", 0) or 0)
        if anchor_override is not None and anchor_override >= 0:
            recorded = int(anchor_override)
        anchors.append(normalize_anchor_latent_frames(recorded))

    per_entry_anchor = []
    for position, entry in enumerate(entries):
        # el primer chunk nunca se recorta: es el que aporta la cabeza de la línea de tiempo
        anchor = 0 if position == 0 else anchors[position]
        if anchor and not anchor_is_feasible(anchor, int(entry["frames"])):
            frames_in = int(entry["frames"])
            room = max_anchor_latent_frames(frames_in)
            if room < LATENT_HEAD:
                detail = ("ese chunk tiene {} tokens latentes, que se consumirían enteros: "
                          "no puede llevar ancla en absoluto".format(latent_t_for_frames(frames_in)))
            else:
                detail = ("su máximo es {} tokens, porque siempre tiene que conservar 2 tokens "
                          "de contenido propio".format(room))
            raise ValueError(
                "El chunk {} ({} frames) no puede absorber un ancla de {} tokens: {}. "
                "Baja anchor_latent_frames a {} o alarga ese chunk hasta {} frames.".format(
                    int(entry["index"]), frames_in, anchor, detail,
                    normalize_anchor_latent_frames(room) if room >= LATENT_HEAD else 2,
                    min_frames_for_anchor(anchor)))
        per_entry_anchor.append(anchor)

    inconsistent = sorted({anchors[i] for i in range(1, len(entries))})
    blocks = [(int(entry["frames"]) - CHUNK_HEAD) // CHUNK_BLOCK for entry in entries]

    total_frames = CHUNK_HEAD + CHUNK_BLOCK * merge_block_count(blocks, per_entry_anchor)
    total_latent_t = latent_t_for_frames(total_frames)
    total_audio_t = audio_t_for_frames(total_frames)

    video_plan, audio_plan = [], []
    video_cursor = 0
    audio_cursor = 0
    for position, entry in enumerate(entries):
        frames = int(entry["frames"])
        latent_t = latent_t_for_frames(frames)
        audio_t = audio_t_for_frames(frames)
        anchor = per_entry_anchor[position]
        drop_frames = frames_for_latent_t(anchor) if anchor else 0
        drop_audio = frames_to_audio_t_offset(drop_frames) if anchor else 0
        keep_video = latent_t - anchor
        keep_audio = audio_t - drop_audio

        video_plan.append({
            "index": int(entry["index"]),
            "latent_slice": (anchor, latent_t),
            "keep_frames": keep_video,
            "start_latent": video_cursor,
        })
        audio_plan.append({
            "index": int(entry["index"]),
            "audio_slice": (drop_audio, audio_t),
            "keep_frames": keep_audio,
            "start_audio": audio_cursor,
        })
        video_cursor += keep_video
        audio_cursor += keep_audio

    audio_drift = total_audio_t - audio_cursor

    return {
        "entries": entries,
        "anchors": per_entry_anchor,
        "distinct_anchors": inconsistent,
        "video": video_plan,
        "audio": audio_plan,
        "total_frames": total_frames,
        "total_latent_t": total_latent_t,
        "total_audio_t": total_audio_t,
        "video_cursor": video_cursor,
        "audio_cursor": audio_cursor,
        "audio_drift": audio_drift,
        "seconds": frames_to_seconds(total_frames),
    }


def apply_merge(videos: list, audios: list, plan: dict) -> tuple:
    """Aplica el plan de fusión. Recorta, concatena y ajusta la deriva de redondeo del audio."""
    video_parts, audio_parts = [], []
    for position, (video, audio) in enumerate(zip(videos, audios)):
        vs = plan["video"][position]
        as_ = plan["audio"][position]
        v0, v1 = vs["latent_slice"]
        a0, a1 = as_["audio_slice"]
        video_parts.append(video[:, :, v0:v1])
        audio_parts.append(audio[..., a0:a1])

    video_out = torch.cat(video_parts, dim=2).contiguous()

    # El audio fusionado debe medir exactamente audio_t_for_frames(total_frames). Cada
    # corte redondea por su cuenta, así que la diferencia se absorbe en el último chunk.
    if plan["audio_drift"] > 0:
        last = audio_parts[-1]
        audio_parts[-1] = torch.cat(
            [last, last[..., -1:].expand(-1, -1, -1, plan["audio_drift"])], dim=-1).contiguous()
    elif plan["audio_drift"] < 0:
        excess = -plan["audio_drift"]
        if excess > audio_parts[-1].shape[-1]:
            raise ValueError(
                "La deriva de audio ({}) supera el último chunk ({}). "
                "Prueba con anchor_latent_frames = 2 o revisa los chunks.".format(
                    excess, audio_parts[-1].shape[-1]))
        audio_parts[-1] = audio_parts[-1][..., :audio_parts[-1].shape[-1] - excess].contiguous()

    audio_out = torch.cat(audio_parts, dim=-1).contiguous()
    return video_out, audio_out


def validate_merged(video: torch.Tensor, audio: torch.Tensor, plan: dict) -> list:
    """Invariantes que el latente fusionado debe cumplir. Devuelve la lista de problemas."""
    problems = []
    latent_t = int(video.shape[2])
    if latent_t != plan["total_latent_t"]:
        problems.append("latent_t fusionado {} != esperado {}".format(latent_t, plan["total_latent_t"]))
    if not is_valid_latent_t(latent_t):
        problems.append("latent_t {} no está en la rejilla 5k+2".format(latent_t))
    if frames_for_latent_t(latent_t) != plan["total_frames"]:
        problems.append("frames {} != esperado {}".format(
            frames_for_latent_t(latent_t), plan["total_frames"]))
    if int(audio.shape[-1]) != plan["total_audio_t"]:
        problems.append("audio_t fusionado {} != esperado {}".format(
            int(audio.shape[-1]), plan["total_audio_t"]))
    if int(audio.shape[-1]) != audio_t_for_frames(plan["total_frames"]):
        problems.append("audio_t no corresponde a round(frames*{})".format(AUDIO_RESCALE))
    # Todas las costuras deben caer en la misma fase del ciclo FRAME_PER_TOKEN
    for step in plan["video"][1:]:
        start = int(step["start_latent"])
        if start % LATENT_BLOCK != LATENT_HEAD:
            problems.append("la costura del chunk {} empieza en {} (mod 5 = {}), se esperaba 2".format(
                step["index"], start, start % LATENT_BLOCK))
    return problems
