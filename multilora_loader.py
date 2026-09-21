UPSTREAM = None  # nodo original de SergioNodes; el reader de metadatos se inspira en AcademiaSD

import json
import os
import struct
import asyncio

import comfy.sd
import comfy.utils
import folder_paths
from server import PromptServer
from aiohttp import web

# ---------------------------------------------------------------------------
# Metadata reader – safe: only reads the safetensors JSON header, never loads
# weights.  The structured layout is inspired by AcademiaSD but kept as a
# single self-contained helper with no external dependencies.
# ---------------------------------------------------------------------------

_MAX_VAL = 68
_MAX_LINES = 46

_GRUPOS = [
    ("\u2699\ufe0f", "TRAINING", [
        ("ss_network_module",             "Network"),
        ("ss_network_dim",                "Dim"),
        ("ss_network_alpha",              "Alpha"),
        ("ss_learning_rate",              "Learning rate"),
        ("ss_unet_lr",                    "UNet LR"),
        ("ss_text_encoder_lr",            "TE LR"),
        ("ss_lr_scheduler",               "Scheduler"),
        ("ss_lr_warmup_steps",            "Warmup"),
        ("ss_optimizer",                  "Optimizer"),
        ("ss_max_train_steps",            "Steps"),
        ("ss_epoch",                      "Epochs"),
        ("ss_num_train_images",           "Images"),
        ("ss_batch_size_per_device",      "Batch"),
        ("ss_gradient_accumulation_steps", "Grad accum"),
        ("ss_mixed_precision",            "Precision"),
        ("ss_seed",                       "Seed"),
        ("ss_noise_offset",               "Noise offset"),
        ("ss_clip_skip",                  "Clip skip"),
    ]),
    ("\U0001f3ac", "DATA", [
        ("ss_resolution",                 "Resolution"),
        ("ss_num_frames",                 "Frames"),
        ("ss_num_batches_per_epoch",      "Batches/epoch"),
        ("ss_num_reg_images",             "Reg images"),
        ("ss_keep_tokens",                "Keep tokens"),
        ("ss_shuffle_caption",            "Shuffle caption"),
    ]),
    ("\U0001f527", "FORMAT", [
        ("format",                        "Format"),
        ("lora_key_prefix",               "Key prefix"),
        ("qkv_fused",                     "QKV fused"),
        ("swiglu_fc1_halves_swapped",     "SwiGLU swapped"),
        ("baked_scaling",                 "Baked scaling"),
        ("modelspec.implementation",      "Implementation"),
    ]),
]

_CABECERA = [
    ("ss_output_name",        "\U0001f4e6"),
    ("project_name",          "\U0001f4e6"),
    ("trained_with",          "\U0001f3ed"),
    ("ss_sd_model_name",      "\U0001f9e0"),
    ("ss_base_model_version", "\U0001f9e0"),
]

_YA_MOSTRADAS = set(k for k, _ in _CABECERA)
for _ico, _tit, pares in _GRUPOS:
    _YA_MOSTRADAS.update(k for k, _ in pares)
_YA_MOSTRADAS.update({"trigger_word", "ss_tag_frequency", "modelspec.trigger_words"})


def _corta(valor, limite=_MAX_VAL):
    v = str(valor).replace("\n", " ").strip()
    if len(v) <= limite:
        return v
    if v[:1] in "[{":
        return "{}... ({} chars)".format(v[: limite - 18], len(v))
    return v[: limite - 3] + "..."


def _read_lora_metadata(lora_path):
    if not lora_path or not os.path.exists(lora_path):
        return "File not found."
    if not lora_path.endswith(".safetensors"):
        return "Metadata reading only supported for .safetensors files."

    try:
        with open(lora_path, "rb") as f:
            header_size = struct.unpack("<Q", f.read(8))[0]
            header = json.loads(f.read(header_size).decode("utf-8"))

        metadata = header.get("__metadata__", {})
        if not metadata:
            return "No training metadata found in this LoRA."

        out = []

        # --- cabecera ---
        vistas = set()
        for clave, icono in _CABECERA:
            v = metadata.get(clave)
            if v and str(v) not in vistas:
                vistas.add(str(v))
                out.append("{}  {}".format(icono, _corta(v)))

        # --- trigger ---
        tags = {}
        crudo = metadata.get("ss_tag_frequency", "")
        if crudo:
            try:
                for _ds, ds_tags in json.loads(crudo).items():
                    for tag, count in ds_tags.items():
                        tags[tag] = tags.get(tag, 0) + count
            except Exception:
                pass

        trigger = metadata.get("trigger_word") or metadata.get(
            "modelspec.trigger_words", ""
        )
        if trigger:
            out.append("")
            out.append("\U0001f3f7\ufe0f  TRIGGER")
            out.append("    " + _corta(trigger))

        if tags:
            orden = sorted(tags.items(), key=lambda x: (-x[1], x[0]))
            if any(c > 1 for _t, c in orden):
                lista = ", ".join("{} ({})".format(t, c) for t, c in orden[:20])
            else:
                lista = ", ".join(t for t, _ in orden[:20])
            if len(orden) > 20:
                lista += ", +{} more".format(len(orden) - 20)
            out.append("")
            out.append("\U0001f3f7\ufe0f  TAGS ({})".format(len(orden)))
            linea = "    "
            for trozo in lista.split(", "):
                if len(linea) + len(trozo) > 54:
                    out.append(linea.rstrip(", "))
                    linea = "    "
                linea += trozo + ", "
            if linea.strip(" ,"):
                out.append(linea.rstrip(", "))

        # --- grupos ---
        for icono, titulo, pares in _GRUPOS:
            filas = [
                (et, metadata[c]) for c, et in pares if metadata.get(c) not in (None, "")
            ]
            if not filas:
                continue
            out.append("")
            out.append("{}  {}".format(icono, titulo))
            ancho = max(len(et) for et, _ in filas)
            for et, v in filas:
                out.append(
                    "    {}  {}".format(
                        et.ljust(ancho), _corta(v, max(20, _MAX_VAL - ancho))
                    )
                )

        # --- resto ---
        resto = sorted(k for k in metadata if k not in _YA_MOSTRADAS)
        if resto:
            out.append("")
            out.append("\U0001f4c4  OTHER ({})".format(len(resto)))
            ancho = min(26, max(len(k) for k in resto))
            for k in resto:
                out.append(
                    "    {}  {}".format(
                        k.ljust(ancho), _corta(metadata[k], max(20, _MAX_VAL - ancho))
                    )
                )

        if len(out) > _MAX_LINES:
            sobran = len(out) - _MAX_LINES
            out = out[:_MAX_LINES] + ["", "    ... +{} more lines".format(sobran)]

        return "\n".join(out) if out else "Metadata exists, but it is empty."

    except Exception as e:
        return "Error reading metadata: {}".format(e)


# ---------------------------------------------------------------------------
# Server routes
# ---------------------------------------------------------------------------

@PromptServer.instance.routes.get("/sergionodes/lora_list")
async def _lora_list(request):
    return web.json_response(folder_paths.get_filename_list("loras"))


@PromptServer.instance.routes.post("/sergionodes/lora_info")
async def _lora_info(request):
    data = await request.json()
    name = data.get("name")
    if not name or name == "None":
        return web.json_response({"info": "No LoRA selected."})
    path = folder_paths.get_full_path("loras", name)
    info = await asyncio.to_thread(_read_lora_metadata, path)
    return web.json_response({"info": info})


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------

class MultiLoraLoader:
    """Load and chain multiple LoRAs in a single node with per-LoRA toggle
    and strength control.  The actual list is stored as a JSON string in a
    hidden STRING widget; all UI is driven by the companion JS extension."""

    DESCRIPTION = (
        "Loads and chains several LoRAs in one node, each with its own enable "
        "toggle and strength, driven by the companion JS extension. Optionally "
        "patches the CLIP when the Standard (Native) injection method is used."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": ("MODEL",),
                "injection_method": (["Standard (Native)", "Model Only (No CLIP)"],),
                "lora_data": ("STRING", {"default": "[]"}),
            },
            "optional": {
                "clip": ("CLIP", {"default": None}),
            },
        }

    RETURN_TYPES = ("MODEL", "CLIP")
    RETURN_NAMES = ("MODEL", "CLIP")
    FUNCTION = "apply_loras"
    CATEGORY = "Sergio Nodes"

    def apply_loras(self, model, injection_method, lora_data="[]", clip=None):
        try:
            loras = json.loads(lora_data)
        except Exception:
            loras = []

        if not loras:
            return (model, clip)

        for lora in loras:
            if not lora.get("enabled", True):
                continue

            name = lora.get("name")
            if not name or name == "None":
                continue

            strength = float(lora.get("strength", 1.0))
            if strength == 0.0:
                continue

            path = folder_paths.get_full_path("loras", name)
            if not path:
                continue

            try:
                tensor = comfy.utils.load_torch_file(path, safe_load=True)
            except Exception:
                continue

            strength_model = strength
            strength_clip = (
                strength
                if injection_method == "Standard (Native)" and clip is not None
                else 0.0
            )

            model, clip = comfy.sd.load_lora_for_models(
                model, clip, tensor, strength_model, strength_clip
            )

        return (model, clip)


NODE_CLASS_MAPPINGS = {"SergioNodes_MultiLora": MultiLoraLoader}
NODE_DISPLAY_NAME_MAPPINGS = {"SergioNodes_MultiLora": "Multi-Lora Loader"}
