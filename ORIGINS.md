# ORIGINS — mapa de orígenes de SergioNodes

Cada fichero del pack declara su nodo original mediante la constante
`UPSTREAM` (en Python) o `const UPSTREAM` (en los JS de `web/`). Formato:

```python
UPSTREAM = ("Nombre del nodo upstream", "https://github.com/user/repo", "ClassId_Upstream")
UPSTREAM = None  # creación original de SergioNodes (sin upstream)
```

Este manifiesto centraliza esa información para las comprobaciones de
actualización: cuando se pida revisar updates, se compara contra el repo
listado aquí **manteniendo siempre la organización/estructura de SergioNodes**
(el port puede quedarse atrás respecto a upstream de forma intencionada).

## Nodos registrados

| Nodo (Sergio) | Node id registrado | Nodo upstream | Repo upstream | Lic. | Estado del port |
|---|---|---|---|---|---|
| Resolution Selector | `Resolution_Selector` / clase `AcademiaResolutionCalc` | Academia SD Resolution Calc | [AcademiaSD/comfyui_AcademiaSD](https://github.com/AcademiaSD/comfyui_AcademiaSD) | — | Reimplementado, misma API de cálculo |
| KSampler Config | `KSamplerConfig` | KSampler Config | [rgthree/rgthree-comfy](https://github.com/rgthree/rgthree-comfy) | — | Clon sin dependencias |
| Unet Loader (GGUF) | `UnetLoaderGGUF` | UnetLoaderGGUF | [city96/ComfyUI-GGUF](https://github.com/city96/ComfyUI-GGUF) | Apache-2.0 | Port parcial (solo imagen/UNet) |
| CLIPLoader (GGUF) | `CLIPLoaderGGUF` | CLIPLoaderGGUF | [city96/ComfyUI-GGUF](https://github.com/city96/ComfyUI-GGUF) | Apache-2.0 | Port parcial |
| Multi-Lora Loader | `SergioNodes_MultiLora` / `MultiLoraLoader` | — (original) | — | MIT | Original; el reader de metadatos se inspira en `AcademiaSD` (
[comfyui_AcademiaSD](https://github.com/AcademiaSD/comfyui_AcademiaSD) ) |
| NKDFaceRig | `NKDFaceRig` | 😺NKD Face Rig | [Nekodificador/ComfyUI-NKD-Basic-Tools](https://github.com/Nekodificador/ComfyUI-NKD-Basic-Tools) | GPL-3.0 | Port adaptado a API V3 |
| Trix Bypass | `TrixBypasser` / `TrixBypasserSimple` | Trix Bypass | [buserror/comfyui-trixnodes](https://github.com/buserror/comfyui-trixnodes) | GPL-3.0 | Port adaptado a Nodes 2.0 (necesita desactivar el pack original) |
| Preview Video | `PreviewVideo` / `SergioNodes_PreviewVideo` | — (original) | — | MIT | Original (hueco entre Preview Image y Save Video) |
| Compare Videos | `CompareVideos` / `SergioNodes_CompareVideos` | — (original, espeja el Compare Images nativo) | — | MIT | Original |
| Minimax H3 Latent Upscaler (3D) | `MinimaxH3LatentUpscaler3D` | Minimax H3 Latent Upscaler (3D) | [xmarre/Comfyui_Minimax_h3_latent_Upscaler](https://github.com/xmarre/Comfyui_Minimax_h3_latent_Upscaler) (fork: [LBH-123-AI](https://github.com/LBH-123-AI/Comfyui_Minimax_h3_latent_Upscaler)) | — | Clon local autónomo |
| DLSS5 Settings | `DLSS5Settings` | — | — | — | Ver DLSS5 |
| DLSS5 Enhance Images | `DLSS5EnhanceImages` | — | — | — | Ver DLSS5 |
| DLSS5 Enhance Video File | `DLSS5EnhanceVideoFile` | — | — | — | Ver DLSS5 |

## DLSS5 (subpack `nodes/` + motor `dlss5/`)

| Fichero | Clase | Node id upstream | Repo upstream | Notas |
|---|---|---|---|---|
| `nodes/settings_node.py`, `nodes/enhance_images.py`, `nodes/enhance_video.py`, `nodes/common.py` | DLSS5Settings / DLSS5EnhanceImages / DLSS5EnhanceVideoFile | `DLSS5Settings`,`DLSS5EnhanceImages`,`DLSS5EnhanceVideoFile` | [Blueforcer/ComfyUI-DLSS5-Enhancer](https://github.com/Blueforcer/ComfyUI-DLSS5-Enhancer) | Mismos node ids (compatibilidad de workflows); interfaz refactorizada |
| `dlss5/*.py`, `install_runtime.py`, `selftest.py` | — | — (motores internos) | — | Implementación original de SergioNodes; runtime nativo desde [Merserk/dlss5-visual-enhancer](https://github.com/Merserk/dlss5-visual-enhancer) (NVIDIA nvngx DLSS5 + ReShade/RenoDX) |

## Ficheros de soporte

| Fichero | Nodo upstream | Repo upstream | Lic. | Notas |
|---|---|---|---|---|
| `gguf_nodes.py` | UnetLoaderGGUF / CLIPLoaderGGUF | [city96/ComfyUI-GGUF](https://github.com/city96/ComfyUI-GGUF) | Apache-2.0 | Port parcial |
| `gguf_loader.py` | gguf_sd_loader / gguf_clip_loader | [city96/ComfyUI-GGUF](https://github.com/city96/ComfyUI-GGUF) | Apache-2.0 | Módulos internos del port |
| `gguf_ops.py` | GGMLOps | [city96/ComfyUI-GGUF](https://github.com/city96/ComfyUI-GGUF) | Apache-2.0 | Módulos internos del port |
| `gguf_convert.py` | converter (subset detección de arquitectura) | [city96/ComfyUI-GGUF](https://github.com/city96/ComfyUI-GGUF) | Apache-2.0 | Minificado |
| `gguf_dequant.py` | descuantización | [city96/ComfyUI-GGUF](https://github.com/city96/ComfyUI-GGUF) | Apache-2.0 | Módulos internos del port |
| `nkd_face_rig.py` | 😺NKD Face Rig | [Nekodificador/ComfyUI-NKD-Basic-Tools](https://github.com/Nekodificador/ComfyUI-NKD-Basic-Tools) | GPL-3.0 | Nodo |
| `nkd_face_core.py` | NKD crop/mask/landmarks | [Nekodificador/ComfyUI-NKD-Basic-Tools](https://github.com/Nekodificador/ComfyUI-NKD-Basic-Tools) | GPL-3.0 | Módulos internos del port |
| `nkd_face_rig_axes.py` | NKD Face Rig (axes) | [Nekodificador/ComfyUI-NKD-Basic-Tools](https://github.com/Nekodificador/ComfyUI-NKD-Basic-Tools) | GPL-3.0 | Módulos internos del port |
| `nkd_face_rig_engine.py` | NKD Face Rig (motor LivePortrait) | [Nekodificador/ComfyUI-NKD-Basic-Tools](https://github.com/Nekodificador/ComfyUI-NKD-Basic-Tools) | GPL-3.0 | LivePortrait MIT (ver `NOTICE.liveportrait`) |
| `nkd_face_rig_routes.py` | NKD Face Rig (backend editor) | [Nekodificador/ComfyUI-NKD-Basic-Tools](https://github.com/Nekodificador/ComfyUI-NKD-Basic-Tools) | GPL-3.0 | Módulos internos del port |
| `nkd_support.py` | NKD helpers (subset `helpers`) | [Nekodificador/ComfyUI-NKD-Basic-Tools](https://github.com/Nekodificador/ComfyUI-NKD-Basic-Tools) | GPL-3.0 | Extraído del pack original |
| `mask_core.py` | NKD Mask Ops (motor) | [Nekodificador/ComfyUI-NKD-Basic-Tools](https://github.com/Nekodificador/ComfyUI-NKD-Basic-Tools) | GPL-3.0 | Módulos internos del port |
| `blur_core.py` | NKD Vector Mask / Path Blur / Field Blur (motor) | [Nekodificador/ComfyUI-NKD-Basic-Tools](https://github.com/Nekodificador/ComfyUI-NKD-Basic-Tools) | GPL-3.0 | Módulos internos del port |
| `utils/human_landmark_runner.py` | NKD (YuNet/landmarks ONNX) | [Nekodificador/ComfyUI-NKD-Basic-Tools](https://github.com/Nekodificador/ComfyUI-NKD-Basic-Tools) | GPL-3.0 | Detector descargado al primer uso |
| `modules/*.py`, `utils/crop.py`, `utils/camera.py`, `utils/rprint.py`, `utils/timer.py`, `config/models.yaml` | LivePortrait (módulos/utils) | [KwaiVGI/LivePortrait](https://github.com/KwaiVGI/LivePortrait) | MIT | Vendidos vía el pack NKD |
| `web/nkd_vue_widgets.js` | NKD Face Rig (bundle frontend; incluye Vue 3.5, MIT) | [Nekodificador/ComfyUI-NKD-Basic-Tools](https://github.com/Nekodificador/ComfyUI-NKD-Basic-Tools) | GPL-3.0 / MIT | Bundle vendido |
| `web/resolution_selector.js` | Academia SD Resolution Calc | [AcademiaSD/comfyui_AcademiaSD](https://github.com/AcademiaSD/comfyui_AcademiaSD) | — | Extensión UI |
| `web/trix_bypasser.js` | Trix Bypass | [buserror/comfyui-trixnodes](https://github.com/buserror/comfyui-trixnodes) | GPL-3.0 | Port a Nodes 2.0 |
| `web/multilora_loader.js` | — (original) | — | MIT | Original SergioNodes |
| `web/node_id_menu.js` | — (original) | — | MIT | Original SergioNodes |