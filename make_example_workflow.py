"""Genera el workflow de ejemplo de H3 Long Video (formato UI de ComfyUI).

Escribir este JSON a mano es pedir que un id de enlace no cuadre, asi que el grafo
se construye con un helper que lleva la cuenta de ids y enlaces. La lista de nodos
y los nombres de widget se hancontrastado contra /object_info del ComfyUI real.
"""
from __future__ import annotations

UPSTREAM = None  # herramienta original de SergioNodes (no es un nodo; no expone schema)

import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(_HERE, "example_workflows", "h3_long_3x124_example.json")

PROJECT = "h3_long_3x5s"
UNET = "Minimax H3/Minimax-h3_Singularity_ref2va_Pruned_v1.3_int8.safetensors"
CLIP = "Minimax H3/qwen3vl_32b_heretic_minimax_h3_nvfp4.safetensors"
VAE_VIDEO = "Minimax H3/minimax_h3_video_vae_fp16.safetensors"
VAE_AUDIO = "Minimax H3/minimax_h3_audio_vae_fp32.safetensors"

PROMPT_1 = ("A lone lighthouse on a storm coast at dusk, slow dolly in, volumetric fog, "
            "cinematic, 35mm, no text")
PROMPT_2 = ("The camera keeps pushing toward the lighthouse, the beam starts sweeping, "
            "waves crash against the rocks, same lighting and palette, cinematic")
PROMPT_3 = ("The lighthouse beam sweeps past camera, spray blows across the lens, "
            "the sky clears a little, same lighthouse and coast, cinematic")

NODES = []
LINKS = []
NEXT_NODE = [1]
NEXT_LINK = [1]


def add_node(node_type, pos, size, widgets=None, inputs=None, outputs=None,
             title=None, color=None):
    node_id = NEXT_NODE[0]
    NEXT_NODE[0] += 1
    node = {
        "id": node_id,
        "type": node_type,
        "pos": list(pos),
        "size": list(size),
        "flags": {},
        "order": node_id - 1,
        "mode": 0,
        "inputs": inputs or [],
        "outputs": outputs or [],
        "properties": {"Node name for S&R": node_type},
        "widgets_values": widgets if widgets is not None else [],
    }
    if title:
        node["title"] = title
    if color:
        node["color"] = color
    NODES.append(node)
    return node


def output(node, name, link_type):
    node["outputs"].append({"name": name, "type": link_type, "links": [], "slot_index": 0})


def main():
    # ---------------- modelos ----------------
    unet = add_node("UNETLoader", [40, 60], [400, 100], [UNET, "default"],
                    title="1. DiT de MiniMax H3 (ref2va)", color="#3f789e")
    output(unet, "MODEL", "MODEL")

    clip = add_node("CLIPLoader", [40, 200], [400, 130], [CLIP, "minimax", "default"],
                    title="2. Qwen3-VL de MiniMax H3", color="#3f789e")
    output(clip, "CLIP", "CLIP")

    vae_v = add_node("VAELoader", [40, 370], [400, 80], [VAE_VIDEO],
                     title="3. VAE de video", color="#3f789e")
    output(vae_v, "VAE", "VAE")

    vae_a = add_node("VAELoader", [40, 490], [400, 80], [VAE_AUDIO],
                     title="4. VAE de audio", color="#3f789e")
    output(vae_a, "VAE", "VAE")

    # ---------------- proyecto ----------------
    project = add_node("MinimaxH3Project", [40, 610], [420, 130], [PROJECT, True, False],
                       title="5. Proyecto (crea la carpeta)", color="#8899aa")
    for slot, (name, kind) in enumerate([("project", "STRING"), ("path", "STRING"),
                                         ("next_index", "INT"), ("chunk_count", "INT"),
                                         ("report", "STRING")]):
        project["outputs"].append({"name": name, "type": kind, "links": [], "slot_index": slot})

    # ---------------- chunk 1 ----------------
    anchor1 = add_node("MinimaxH3ChunkAnchor", [520, 60], [420, 420],
                       [PROJECT, 1, PROMPT_1, 5.0, 1344, 768, 2, "trim", "match"],
                       title="6. Chunk 1 (sin ancla: abre la historia)", color="#aacc88")
    for slot, (name, kind) in enumerate([("positive", "CONDITIONING"), ("LATENT", "LATENT"),
                                         ("frames_back", "INT"), ("report", "STRING")]):
        anchor1["outputs"].append({"name": name, "type": kind, "links": [], "slot_index": slot})

    neg1 = add_node("ConditioningZeroOut", [520, 520], [220, 60], None,
                    title="negativo = positivo a cero", color="#666")
    output(neg1, "CONDITIONING", "CONDITIONING")

    sampler1 = add_node("KSampler", [1000, 60], [340, 260],
                        [42, 28, 5.0, "euler", "simple", 1.0],
                        title="7. Muestrear chunk 1", color="#A88")
    output(sampler1, "LATENT", "LATENT")

    vault1 = add_node("MinimaxH3ChunkVault", [1000, 360], [420, 160], [PROJECT, 1, -1],
                      title="8. Guardar chunk 1 en disco", color="#88A")
    for slot, (name, kind) in enumerate([("LATENT", "LATENT"), ("next_index", "INT"),
                                         ("saved_mb", "FLOAT"), ("report", "STRING")]):
        vault1["outputs"].append({"name": name, "type": kind, "links": [], "slot_index": slot})

    # ---------------- chunk 2 (descomentado para continuar) ----------------
    anchor2 = add_node("MinimaxH3ChunkAnchor", [520, 620], [420, 420],
                       [PROJECT, 2, PROMPT_2, 5.0, 1344, 768, 2, "trim", "match"],
                       title="9. Chunk 2 (anclado al chunk 1)", color="#aacc88")
    anchor2["mode"] = 2   # apagado hasta que exista el chunk 1
    for slot, (name, kind) in enumerate([("positive", "CONDITIONING"), ("LATENT", "LATENT"),
                                         ("frames_back", "INT"), ("report", "STRING")]):
        anchor2["outputs"].append({"name": name, "type": kind, "links": [], "slot_index": slot})

    neg2 = add_node("ConditioningZeroOut", [520, 1080], [220, 60], None, color="#666")
    neg2["mode"] = 2
    output(neg2, "CONDITIONING", "CONDITIONING")

    sampler2 = add_node("KSampler", [1000, 620], [340, 260],
                        [43, 28, 5.0, "euler", "simple", 1.0],
                        title="10. Muestrear chunk 2", color="#A88")
    sampler2["mode"] = 2
    output(sampler2, "LATENT", "LATENT")

    vault2 = add_node("MinimaxH3ChunkVault", [1000, 920], [420, 160], [PROJECT, 2, -1],
                      title="11. Guardar chunk 2", color="#88A")
    vault2["mode"] = 2
    for slot, (name, kind) in enumerate([("LATENT", "LATENT"), ("next_index", "INT"),
                                         ("saved_mb", "FLOAT"), ("report", "STRING")]):
        vault2["outputs"].append({"name": name, "type": kind, "links": [], "slot_index": slot})

    # ---------------- chunk 3 ----------------
    anchor3 = add_node("MinimaxH3ChunkAnchor", [520, 1180], [420, 420],
                       [PROJECT, 3, PROMPT_3, 5.0, 1344, 768, 2, "trim", "match"],
                       title="12. Chunk 3 (anclado al chunk 2)", color="#aacc88")
    anchor3["mode"] = 2
    for slot, (name, kind) in enumerate([("positive", "CONDITIONING"), ("LATENT", "LATENT"),
                                         ("frames_back", "INT"), ("report", "STRING")]):
        anchor3["outputs"].append({"name": name, "type": kind, "links": [], "slot_index": slot})

    neg3 = add_node("ConditioningZeroOut", [520, 1640], [220, 60], None, color="#666")
    neg3["mode"] = 2
    output(neg3, "CONDITIONING", "CONDITIONING")

    sampler3 = add_node("KSampler", [1000, 1180], [340, 260],
                        [44, 28, 5.0, "euler", "simple", 1.0],
                        title="13. Muestrear chunk 3", color="#A88")
    sampler3["mode"] = 2
    output(sampler3, "LATENT", "LATENT")

    vault3 = add_node("MinimaxH3ChunkVault", [1000, 1480], [420, 160], [PROJECT, 3, -1],
                      title="14. Guardar chunk 3", color="#88A")
    vault3["mode"] = 2
    for slot, (name, kind) in enumerate([("LATENT", "LATENT"), ("next_index", "INT"),
                                         ("saved_mb", "FLOAT"), ("report", "STRING")]):
        vault3["outputs"].append({"name": name, "type": kind, "links": [], "slot_index": slot})

    # ---------------- fusion y salida ----------------
    # El grupo de exportacion va MUTEADO de origen, por dos razones:
    #  1) Merge lee de disco y no depende del Vault por ningun cable, asi que dentro
    #     de la misma ejecucion podria correr antes de que se escribiera el chunk.
    #  2) En el run 1 no hay ningun chunk guardado, y Merge fallaria.
    merge = add_node("MinimaxH3MergeProject", [1500, 620], [440, 320],
                     [PROJECT, 1, 0, -1, "h3_long"],
                     title="15. Fusionar (1..0 = todos los chunks)", color="#c8a0d0")
    merge["mode"] = 2
    for slot, (name, kind) in enumerate([("LATENT", "LATENT"), ("frames", "INT"),
                                         ("duration_seconds", "FLOAT"), ("report", "STRING")]):
        merge["outputs"].append({"name": name, "type": kind, "links": [], "slot_index": slot})

    dec_v = add_node("VAEDecode", [2000, 620], [260, 80], None,
                     title="16. Decodificar video", color="#8a8")
    dec_v["mode"] = 2
    output(dec_v, "IMAGE", "IMAGE")

    dec_a = add_node("VAEDecodeAudio", [2000, 740], [260, 80], None,
                     title="17. Decodificar audio", color="#8a8")
    dec_a["mode"] = 2
    output(dec_a, "AUDIO", "AUDIO")

    # Solo se fijan los widgets que queremos controlar; los de atras los rellena el
    # frontend con el default del schema. Escribirlos a mano era justo lo que
    # rompia el prompt ("bit_depth: '8' not in ['auto', 8, 10]"), y los
    # COMFY_DYNAMICCOMBO_V3 de SaveVideo no se pueden serializar a mano de forma fiable.
    video = add_node("CreateVideo", [2320, 620], [300, 160], [24],
                     title="18. Empaquetar AV (fps)", color="#8a8")
    video["mode"] = 2
    output(video, "VIDEO", "VIDEO")

    save = add_node("SaveVideo", [2680, 620], [340, 200], ["h3_long/merged"],
                    title="19. Guardar video", color="#8a8")
    save["mode"] = 2
    output(save, "VIDEO", "VIDEO")

    # ---------------- enlaces ----------------
    plan = [
        (project, 0, anchor1, "project", "STRING"),
        (project, 0, anchor2, "project", "STRING"),
        (project, 0, anchor3, "project", "STRING"),
        (project, 0, vault1, "project", "STRING"),
        (project, 0, vault2, "project", "STRING"),
        (project, 0, vault3, "project", "STRING"),
        (project, 0, merge, "project", "STRING"),
        (clip, 0, anchor1, "clip", "CLIP"),
        (clip, 0, anchor2, "clip", "CLIP"),
        (clip, 0, anchor3, "clip", "CLIP"),
        (vae_v, 0, anchor1, "vae", "VAE"),
        (vae_v, 0, anchor2, "vae", "VAE"),
        (vae_v, 0, anchor3, "vae", "VAE"),
        (anchor1, 0, neg1, "conditioning", "CONDITIONING"),
        (unet, 0, sampler1, "model", "MODEL"),
        (anchor1, 0, sampler1, "positive", "CONDITIONING"),
        (neg1, 0, sampler1, "negative", "CONDITIONING"),
        (anchor1, 1, sampler1, "latent_image", "LATENT"),
        (sampler1, 0, vault1, "latent", "LATENT"),
        (anchor2, 0, neg2, "conditioning", "CONDITIONING"),
        (unet, 0, sampler2, "model", "MODEL"),
        (anchor2, 0, sampler2, "positive", "CONDITIONING"),
        (neg2, 0, sampler2, "negative", "CONDITIONING"),
        (anchor2, 1, sampler2, "latent_image", "LATENT"),
        (sampler2, 0, vault2, "latent", "LATENT"),
        (anchor3, 0, neg3, "conditioning", "CONDITIONING"),
        (unet, 0, sampler3, "model", "MODEL"),
        (anchor3, 0, sampler3, "positive", "CONDITIONING"),
        (neg3, 0, sampler3, "negative", "CONDITIONING"),
        (anchor3, 1, sampler3, "latent_image", "LATENT"),
        (sampler3, 0, vault3, "latent", "LATENT"),
        (merge, 0, dec_v, "samples", "LATENT"),
        (merge, 0, dec_a, "samples", "LATENT"),
        (vae_v, 0, dec_v, "vae", "VAE"),
        (vae_a, 0, dec_a, "vae", "VAE"),
        (dec_v, 0, video, "images", "IMAGE"),
        (dec_a, 0, video, "audio", "AUDIO"),
        (video, 0, save, "video", "VIDEO"),
    ]
    for origin, origin_slot, target, target_name, kind in plan:
        link_id = NEXT_LINK[0]
        NEXT_LINK[0] += 1
        LINKS.append([link_id, origin["id"], origin_slot, target["id"], 0, kind])
        target["inputs"].append({"name": target_name, "type": kind, "link": link_id})
        origin["outputs"][origin_slot]["links"].append(link_id)

    workflow = {
        "last_node_id": NEXT_NODE[0] - 1,
        "last_link_id": NEXT_LINK[0] - 1,
        "nodes": NODES,
        "links": LINKS,
        "groups": [
            {"id": 1, "title": "Modelos H3", "bounding": [20, 40, 440, 550], "color": "#3f789e"},
            {"id": 2, "title": "Generar chunk 1", "bounding": [500, 40, 940, 500], "color": "#aacc88"},
            {"id": 3, "title": "Generar chunk 2 (activa al guardar el 1)", "bounding": [500, 600, 940, 500], "color": "#88cc99"},
            {"id": 4, "title": "Generar chunk 3 (activa al guardar el 2)", "bounding": [500, 1160, 940, 500], "color": "#88cc99"},
            {"id": 5, "title": "Fusionar y exportar", "bounding": [1480, 600, 1560, 240], "color": "#c8a0d0"},
        ],
        "config": {},
        "extra": {},
        "version": 0.4,
    }

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as handle:
        json.dump(workflow, handle, indent=2, ensure_ascii=False)
    print("Escrito:", OUT)
    print("Nodos:", len(NODES), " Enlaces:", len(LINKS))
    for node in NODES:
        for slot in node["inputs"]:
            if slot["link"] is not None:
                matching = [item for item in LINKS if item[0] == slot["link"]]
                assert len(matching) == 1, "enlace roto {}".format(slot)
    print("Coherencia de enlaces: OK")


if __name__ == "__main__":
    main()
