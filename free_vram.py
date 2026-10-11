# coding: utf-8
"""
😺SergioNodes Free VRAM — descarga los modelos cargados y vacía la caché de VRAM.

ComfyUI mantiene cada modelo cacheado en VRAM entre nodos para no recargarlo, así
que un modelo de vídeo recién usado sigue ocupando memoria cuando un nodo posterior
(intérprete de prompts, Ollama, etc.) necesita la GPU. Este nodo rompe esa
retención: descarga todos los modelos cacheados, fuerza el vaciado de la caché de
torch y recolecta basura, dejando la VRAM libre para lo que venga después.

Colócalo *entre* el último nodo que usa el modelo pesado y el siguiente nodo que
quiere GPU. Enlaza su passthrough `anything` en la cadena para fijar el orden de
ejecución (entrada → salida), de modo que corra en el momento justo. Como es un
nodo de salida (`is_output_node`), también puedes ejecutarlo solo — sin conectar
nada — pulsando Queue, para vaciar la VRAM a demanda.
"""
from __future__ import annotations

UPSTREAM = None  # nodo original de SergioNodes (sin upstream; cubre la descarga manual de modelos/VRAM)

from typing import Any

from comfy_api.latest import io

import comfy.model_management as mm


def _device_label() -> str:
    try:
        return mm.get_torch_device_name(mm.get_torch_device())
    except Exception:
        return "device"


def _free_gib() -> float:
    try:
        return mm.get_free_memory() / (1024 ** 3)
    except Exception:
        return float("nan")


class FreeVRAM(io.ComfyNode):
    """Descarga modelos y libera la VRAM para los nodos siguientes."""

    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="FreeVRAM",
            display_name="Free VRAM",
            category="Sergio Nodes",
            is_output_node=True,
            search_aliases=[
                "free vram",
                "unload models",
                "empty cache",
                "release gpu",
                "liberar vram",
                "descargar modelos",
                "ollama",
            ],
            description=(
                "Descarga todos los modelos cargados y vacía la caché de VRAM. Útil "
                "entre la generación de vídeo (MiniMax H3, etc.) y un nodo que "
                "necesita la GPU, como un intérprete de prompts por Ollama, que de "
                "otro modo se queda sin VRAM y va lentísimo. Es un nodo de salida: "
                "puedes ejecutarlo solo, sin conectar nada, y también enlazar "
                "`anything` en la cadena para fijar el momento de ejecución."
            ),
            inputs=[
                io.AnyType.Input(
                    "anything",
                    optional=True,
                    tooltip="Passthrough opcional. Enlázalo entre el nodo pesado y el "
                            "siguiente para fijar cuándo se libera la VRAM.",
                ),
                io.Boolean.Input(
                    "unload_models",
                    default=True,
                    label_on="descargar",
                    label_off="solo caché",
                    tooltip="Descarga los modelos cacheados de la VRAM. Desactívalo "
                            "para vaciar únicamente la caché de torch sin soltar los "
                            "modelos cargados.",
                ),
                io.Boolean.Input(
                    "gc_collect",
                    default=True,
                    tooltip="Fuerza una recolección de basura en Python antes de "
                            "vaciar la caché, para soltar referencias circulares de "
                            "modelos ya no usados.",
                ),
            ],
            outputs=[
                io.AnyType.Output(
                    "anything",
                    tooltip="El mismo valor de entrada, sin cambios (passthrough).",
                ),
            ],
        )

    @classmethod
    def execute(cls, anything: Any = None, unload_models: bool = True,
                gc_collect: bool = True) -> io.NodeOutput:
        before = _free_gib()

        if gc_collect:
            import gc

            gc.collect()

        if unload_models:
            mm.unload_all_models()
            mm.cleanup_models()

        mm.soft_empty_cache(force=True)

        after = _free_gib()
        dev = _device_label()
        freed = after - before
        if freed == freed:  # not NaN
            print(f"[SergioNodes] Free VRAM: {freed:+.2f} GiB libres ({dev}, "
                  f"ahora {after:.2f} GiB libres)")
        else:
            print(f"[SergioNodes] Free VRAM: caché vaciada ({dev})")

        return io.NodeOutput(anything)
