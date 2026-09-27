# SergioNodes

Custom nodes para ComfyUI (categoría **Sergio Nodes**). Clónalo en
`ComfyUI/custom_nodes/SergioNodes`.

## Nodos

- **Resolution Selector** — cálculo de resoluciones de salida a partir de una base y orientación.
- **KSampler Config** — generación de config de sampler (steps, cfg, sampler, scheduler, denoise) en un solo socket.
- **Unet Loader (GGUF)** — carga de modelos GGUF de imagen/UNet con soporte de reescalado de dimensiones.
- **CLIPLoader (GGUF)** — carga de CLIP cuantizado GGUF (con reconstrucción de tokenizer opcional).
- **Multi-Lora Loader** — apilado de múltiples LoRAs sobre un modelo base con control de fuerza por socket.
- **NKDFaceRig** — face rigging (port de Face Rig de NKD): animación facial con movimiento, máscaras y preview en canvas. Descarga automáticamente los modelos LivePortrait y de detección (YuNet) al primer uso.
- **Bypass Groups by ID / Bypass Nodes by ID** (`TrixBypasser`/`TrixBypasserSimple`) — bypass/mute de nodos desde el canvas con lista de objetivos, grupos y picker (port de comfyui-trixnodes adaptado a Nodes 2.0 vía DOM widget).
- **Preview Video** (`PreviewVideo`) — previsualización de vídeo en canvas sin guardarlo en la carpeta permanente `output/` (equivalente directo de *Preview Image* para el flujo de vídeo nativo de ComfyUI / `Create Video`).
- **Minimax H3 Latent Upscaler (3D)** (`MinimaxH3LatentUpscaler3D`) — upscaler de latentes MiniMax H3 (clon local del pack Comfyui_Minimax_h3_latent_Upscaler): temporal chunking, alineado a píxel fotográfico, backends cuda/rocm/cpu y 3 modos de tamaño. Modelos en `latent_upscale_models`.
- **Node ID en menú contextual** — extensión frontend que añade "Node ID: N" (con copia al portapapeles) al clic derecho de cualquier nodo.

> Válido para ComfyUI API V3 / Nodes 2.0 y frontend clásico.

## Instalacion

```sh
git clone https://github.com/<tu-usuario>/SergioNodes.git ComfyUI/custom_nodes/SergioNodes
```

Dependencias Python adicionales (comfyui-core ya aporta torch, numpy, PIL):

```sh
pip install -r ComfyUI/custom_nodes/SergioNodes/requirements.txt
```

Si venias de la version antigua, desactiva/elimina los packs originales
(`comfyui-trixnodes`, NKD Face Rig) para no duplicar nodos.

## Notas

- Los pesos de NKDFaceRig se descargan a peticion desde Hugging Face (LivePortrait safetensors + YuNet/adetailer). No se incluyen en el repo.
- El frontend de los nodos vive en `web/` y se carga solo como extension.

## Creditos

- Face Rig: basado en el pack **NKD** (https://github.com/nkd) y **LivePortrait** (MIT), con deteccion **YuNet** y adetailer.
- Trix: port de **comfyui-trixnodes** (https://github.com/buserror/comfyui-trixnodes).

## Licencia

MIT — ver `LICENSE`.