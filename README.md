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
- **MiniMax H3 Long Video (4 nodos)** (`MinimaxH3Project` / `MinimaxH3ChunkAnchor` / `MinimaxH3ChunkVault` / `MinimaxH3MergeProject`) — vídeo largo por chunks con continuidad real de vídeo y audio. Ver la sección de abajo.
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

## MiniMax H3 Long Video

Cuatro nodos para generar video largo con MiniMax H3 (video + audio nativos de ComfyUI)
partiendo la linea de tiempo en chunks que se solapan y se vuelven a unir sin perder
la rejilla temporal que el modelo exige.

### Por que hace falta un solape

MiniMax H3 trabaja con un latent AV anidado: `video[1,24,T,H/16,W/16]` y
`audio[1,32,2,5T/3]`, con una rejilla de frames muy restrictiva:

```
latent_t = 5k + 2
frames   = 17k + 5
audio_t  = round(frames * 5 / 3)
```

El `+2` final del latent es un token de *padding* obligatorio. Por eso **no existe un
corte seco**: si generas `k` bloques y los concatenas, el resultado tiene
`5k + (N-1)*2` tokens, que no esta en la rejilla salvo en el primer chunk, y el
decodificador se queja. La unica forma valida de encadenar es solapar y descartar.

El solape minimo es de **2 tokens latentes** (17 frames de video, ~10 tokens de audio).
Valores `0` o `1` se normalizan a `2` automaticamente; no hay corte seco en v1.

### Los nodos

| Nodo | Que hace |
| --- | --- |
| `MinimaxH3Project` | Crea o abre la carpeta del proyecto en `ComfyUI/output/h3_projects/<nombre>/` e inicializa el indice `project.json`. |
| `MinimaxH3ChunkAnchor` | Construye el latent AV de destino en la rejilla correcta, calcula la ventana de ancla contra el chunk anterior, ancla el final del chunk previo como keyframes nativas y añade las refs. |
| `MinimaxH3ChunkVault` | Guarda el latent muestreado en `chunk_NNNN.safetensors` y registra geometria y politica de ancla en el indice. |
| `MinimaxH3MergeProject` | Une los chunks solapados en un unico latent AV, corrige la deriva de audio y devuelve `LATENT`, `frames`, `duracion` e informe. |

### Flujo

```
Project ─┬─> Chunk Anchor (idx 1) ─> KSampler ─> Chunk Vault (1) ─┐
         │                                                     │
         ├─> Chunk Anchor (idx 2) ─> KSampler ─> Chunk Vault (2) ─┤
         │                                        ^ancla al 1    │
         ├─> Chunk Anchor (idx 3) ─> KSampler ─> Chunk Vault (3) ─┤
         │                                                     │
         └─> Merge Project ─> VAEDecode / VAEDecodeAudio ─> CreateVideo ─> SaveVideo
```

El `Chunk Anchor` lee el chunk anterior **del disco**, no de memoria, asi que puedes
cerrar ComfyUI y continuar otro dia. El solape se ancla con el keyframe nativo
`{"resolved_frame_index", "latent", "audio_latent"}` sobre latentes crudos: no se
denoisea nada, se reproduce exactamente lo que ya se genero.

### Fusion

El ancla se mide en **tokens latentes** y solo admite valores de la forma `5m+2`. Ese
`+2` es la cabeza, de modo que el solape minimo (2 tokens) **no descarta ningun block
completo**: solo la cabeza, 5 frames reales. Si quieres solapar de verdad, sube a 7
tokens (`m=1`), 12 (`m=2`) y asi.

Descontar `5m+2` tokens del frente de un chunk elimina `17m+5` frames reales, o sea
`m` blocks completos **mas** la cabeza, que ya no vale por si sola. Por eso el total de
blocks baja en `m` por union:

```
blocks   = sum(k_i) - m * (N - 1)
frames   = 17 * blocks + 5
latent_t = 5 * blocks + 2
```

**3 chunks de 124 frames** (cada uno `k = (124-5)/17 = 7` blocks, `latent_t = 37`):

| Ancla | m | Por union | blocks | Resultado |
| --- | --- | --- | --- | --- |
| 2 tokens (minimo) | 0 | 5 frames | `21 - 0 = 21` | **362 frames**, 15.08 s, `latent_t=107`, `audio_t=603` |
| 7 tokens | 1 | 22 frames | `21 - 2 = 19` | 328 frames, 13.67 s, `latent_t=97`, `audio_t=547` |
| 12 tokens | 2 | 39 frames | `21 - 4 = 17` | 294 frames, 12.25 s, `latent_t=87`, `audio_t=490` |

Comprobacion con la cuenta de frames: `3 * 124 = 372`, menos 5 frames por union con
ancla 2 → 362. Con ancla 7 son 22 frames por union → `372 - 44 = 328`.

El audio se recorta al final si sobra (el redondeo `5/3` no es exacto), de modo que
el `latent_t` fusionado siempre cae en la rejilla. Con 3x124 y ancla 2 hay que
recortar 2 tokens de audio. El informe del nodo indica si ha habido que ajustar y cuanto.

### Modelos

Solo funciona con el checkpoint **`ref2va`** (el que acepta conditioning e imagenes de
referencia): `Minimax H3/Minimax-h3_Singularity_ref2va_Pruned_v1.3_int8.safetensors`.
El `fl2va` no acepta las refs ni el payload de este flujo.

Necesitas ademas el text encoder (`qwen3vl_32b_heretic_minimax_h3_nvfp4.safetensors`)
y los dos VAE (`minimax_h3_video_vae_fp16.safetensors`,
`minimax_h3_audio_vae_fp32.safetensors`). Si los tienes en otra carpeta, declara las
rutas en el `extra_model_paths.yaml` de la raiz de ComfyUI.

Para decodificar: `VAEDecode` toma el primer stream del latent anidado (video) y
`VAEDecodeAudio` el ultimo (audio). Alimenta los dos desde la misma salida `LATENT` de
`Merge Project`.

### Workflow de ejemplo

`example_workflows/h3_long_3x124_example.json` — 3 chunks de 124 frames. Trae los
cuatro grupos listos, y **solo el primero viene activo**:

1. **Run 1** — grupo 1 (chunk 1).
2. Selecciona los 4 nodos del grupo 2 y quita el mute (Ctrl+M). **Run 2**.
3. Igual con el grupo 3. **Run 3**.
4. Selecciona el grupo 4 entero (fusionar + decodificar + guardar) y quita el mute.
   **Run 4**.

El grupo de exportacion va muteado de origen a proposito: `Merge Project` lee del
disco y no depende del `Chunk Vault` por ningun cable, asi que si estuviera activo en
la misma ejecucion podria correr antes de que se escribiera el chunk, y en el run 1
no hay ningun chunk que fusionar.

`Merge Project` esta en `1..0` (= "todos"), asi que coge lo que haya en el indice.
`anchor_override` en `-1` significa "usa la politica de ancla que grabo cada chunk".

La carpeta del proyecto se crea bajo el **directorio de salida que tenga configurado
ComfyUI** (`output/h3_projects/<nombre>/` por defecto; si usas `--output-directory` o
Comfy Desktop, cambia).

Es lo que evita el tipico workflow que se ve bien en el editor y falla al ejecutar.
Ademas contrasta los valores de cada widget contra las opciones que declara el schema,
que es como se cazan los `Value not in list` de los combos.

### Limites que conviene saber

- **La calidad de la costura no esta garantizada.** La estructura, la rejilla y la
  decodificacion son correctas por construccion; que el resultado no de un salto visible
  entre chunks depende del prompt, del CFG y del modelo. Si se nota, sube `anchor_latent_frames`
  (7 en vez de 2) a costa de perder material.
- **Un chunk por ejecucion.** Es a proposito: la cola de ComfyUI mantiene el estado del
  sampler y el anchor, y asi una desconexion a mitad no rompe el proyecto.
- **Decodificar 362 frames de golpe puede dar OOM.** Si ocurre, decodifica por tramos o
  baja la resolucion; el merge en si es barato.
- El informe de `Chunk Anchor` avisa cuando el chunk receptor es demasiado corto para la
  politica de ancla elegida.
- Las refs usan el mismo payload que el ancla, asi que **solo con `ref2va`**.

`h3_selftest.py` cubre la aritmetica temporal, la paridad con el `temporal_shape` nativo,
la normalizacion de anclas, la seguridad de rutas y 42.720 combinaciones de fusion.
Se ejecuta desde `selftest.py` sin cargar ningun modelo.

## Notas

- Los pesos de NKDFaceRig se descargan a peticion desde Hugging Face (LivePortrait safetensors + YuNet/adetailer). No se incluyen en el repo.
- El frontend de los nodos vive en `web/` y se carga solo como extension.

## Creditos

- Face Rig: basado en el pack **NKD** (https://github.com/nkd) y **LivePortrait** (MIT), con deteccion **YuNet** y adetailer.
- Trix: port de **comfyui-trixnodes** (https://github.com/buserror/comfyui-trixnodes).

## Licencia

MIT — ver `LICENSE`.