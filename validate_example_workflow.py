"""Convierte el workflow de ejemplo (formato UI) a formato API y lo valida.

El backend de ComfyUI no acepta el formato UI, asi que un workflow puede verse
perfecto en el editor y aun asi fallar al ejecutar. Este script lo traduce a
formato API (que es donde estan los nombres de entrada reales) y comprueba:

  - que cada tipo de nodo existe en el backend,
  - que cada widget ordenado corresponde a una entrada declarada,
  - que cada enlace apunta a un socket de entrada que existe,
  - que no queda ningun widget huerfano o entrada requerida sin valor.
"""
from __future__ import annotations

UPSTREAM = None  # herramienta original de SergioNodes (no es un nodo; no expone schema)

import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
WORKFLOW = os.path.join(HERE, "example_workflows", "h3_long_3x124_example.json")
SERVER = "http://127.0.0.1:8188"

# Tipos de la API V3 que son widgets (primitivos) frente a sockets (enlazables).
# COMFY_DYNAMICCOMBO_V3 cuenta como widget: es un combo con valores anidados que el
# editor pinta como widget, no como socket.
PRIMITIVES = ("STRING", "INT", "FLOAT", "BOOLEAN", "COMBO", "COMFY_DYNAMICCOMBO_V3")


def fetch_object_info():
    with urllib.request.urlopen(SERVER + "/object_info", timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def validate(workflow, object_info):
    problems = []
    notes = []
    nodes_by_id = {node["id"]: node for node in workflow["nodes"]}
    api = {}

    for node in workflow["nodes"]:
        node_type = node["type"]
        if node_type not in object_info:
            problems.append("nodo #{} de tipo desconocido: {}".format(node["id"], node_type))
            continue
        spec = object_info[node_type]
        required = list(spec["input"].get("required", {}).keys())
        optional = list(spec["input"].get("optional", {}).keys())

        # Los sockets del workflow deben existir como entradas, y las entradas
        # alimentadas por widget no deben aparecer como socket.
        linked_names = {item["name"] for item in node["inputs"] if item.get("link") is not None}
        for name in linked_names:
            if name not in required and name not in optional:
                problems.append("nodo #{} ({}): enlace hacia una entrada inexistente '{}'".format(
                    node["id"], node_type, name))

        # Entradas primitivas en orden de declaración = orden de widgets.
        widget_inputs = [name for name in required + optional
                         if _kind(spec, name) in PRIMITIVES
                         and not _is_autogrow(spec, name)]
        widgets = node.get("widgets_values", [])
        if len(widgets) > len(widget_inputs):
            problems.append("nodo #{} ({}): {} widgets para {} entradas primitivas".format(
                node["id"], node_type, len(widgets), len(widget_inputs)))
        for name in widget_inputs:
            if name in linked_names:
                # ComfyUI permite soltar un cable sobre un widget: el frontend lo
                # convierte en socket. Es legal, pero conviene confirmarlo en vez de
                # asumirlo, asi que se avisa como nota y no como error.
                notes.append("nodo #{} ({}): '{}' es un widget pero recibe cable "
                             "(el frontend lo mostrara como socket)".format(
                                 node["id"], node_type, name))
                continue
            if position_of(name, widget_inputs) >= len(widgets):
                continue      # widget omitido a proposito: el frontend usa el default
            value = widgets[position_of(name, widget_inputs)]
            options = _combo_options(spec, name)
            if options and not _in_combo(value, options):
                problems.append(
                    "nodo #{} ({}): '{}' = {!r} no esta entre las opciones validas {}".format(
                        node["id"], node_type, name, value, options))

        # Construye el prompt de API
        values = {}
        for position, name in enumerate(widget_inputs):
            if name in linked_names:
                continue
            if position < len(widgets) and widgets[position] is not None:
                values[name] = widgets[position]
        for item in node["inputs"]:
            if item.get("link") is not None:
                values[item["name"]] = [str(item["link"]), 0]
        # los widgets que se enlazan pierden su valor, se rellenan abajo
        api[str(node["id"])] = {"class_type": node_type, "inputs": values,
                                "_meta": {"title": node.get("title", node_type)}}

    # resolver los enlaces -> [origen, slot]
    for entry in workflow["links"]:
        link_id, origin_id, origin_slot, target_id, target_slot, _kind_name = entry
        origin = nodes_by_id.get(origin_id)
        target = api.get(str(target_id))
        if origin is None or target is None:
            problems.append("enlace {} apunta a un nodo inexistente".format(link_id))
            continue
        target_name = next((item["name"] for item in nodes_by_id[target_id]["inputs"]
                            if item.get("link") == link_id), None)
        if target_name is None:
            problems.append("enlace {} no aparece en las entradas del nodo destino".format(link_id))
            continue
        target["inputs"][target_name] = [str(origin_id), origin_slot]

    # valida que no queden entradas requeridas sin valor en los nodos activos
    for node in workflow["nodes"]:
        if node.get("mode", 0) in (2, 4):    # 2 = mute, 4 = bypass
            continue
        node_type = node["type"]
        if node_type not in object_info:
            continue
        spec = object_info[node_type]
        for name in spec["input"].get("required", {}):
            if _kind(spec, name) in PRIMITIVES or _is_autogrow(spec, name):
                continue
            if name not in api[str(node["id"])]["inputs"]:
                problems.append("nodo #{} ({}): entrada requerida sin conectar '{}'".format(
                    node["id"], node_type, name))
    return api, problems, notes


def _kind(spec, name):
    for section in ("required", "optional"):
        entry = spec["input"].get(section, {}).get(name)
        if entry is not None:
            return entry[0] if isinstance(entry[0], str) else "COMBO"
    return None


def position_of(name, widget_inputs):
    """Indice de un widget por su posicion en la lista de entradas primitivas."""
    return widget_inputs.index(name)


def _combo_options(spec, name):
    """Opciones válidas de un COMBO simple, o None si no es un combo."""
    for section in ("required", "optional"):
        entry = spec["input"].get(section, {}).get(name)
        if entry is None:
            continue
        if entry[0] != "COMBO" or len(entry) < 2:
            return None
        options = entry[1].get("options") if isinstance(entry[1], dict) else entry[1]
        if not isinstance(options, list):
            return None
        # Un COMFY_DYNAMICCOMBO_V3 trae options como lista de dicts con 'key'.
        if options and isinstance(options[0], dict):
            return None
        return options
    return None


def _in_combo(value, options):
    """Compare sin confundir 8 (int) con '8' (str): el prompt distingue tipos."""
    for option in options:
        if option == value and type(option) is type(value):
            return True
        if option == value and not isinstance(option, bool) == (value is None or isinstance(value, bool)):
            return True
    return False


def _is_autogrow(spec, name):
    for section in ("required", "optional"):
        entry = spec["input"].get(section, {}).get(name)
        if entry is not None:
            return isinstance(entry[0], str) and entry[0].startswith("COMFY_AUTOGROW")
    return False


def main():
    with open(WORKFLOW, "r", encoding="utf-8") as handle:
        workflow = json.load(handle)
    object_info = fetch_object_info()
    api, problems, notes = validate(workflow, object_info)

    print("Nodos en el workflow: {}".format(len(workflow["nodes"])))
    print("Enlaces:             {}".format(len(workflow["links"])))
    print("Prompt API generado: {} nodos".format(len(api)))
    if notes:
        print("\nNOTAS ({}):".format(len(notes)))
        for line in notes:
            print("  -", line)
    if problems:
        print("\nPROBLEMAS ({}):".format(len(problems)))
        for line in problems:
            print("  -", line)
        return 1
    print("\nVALIDACION DEL WORKFLOW: OK")
    out = os.path.join(HERE, "example_workflows", "h3_long_3x124_example.api.json")
    with open(out, "w", encoding="utf-8") as handle:
        json.dump(api, handle, indent=2, ensure_ascii=False)
    print("Prompt API guardado en:", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
