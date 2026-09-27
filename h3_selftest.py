# coding: utf-8
"""
😺SergioNodes — selftest de la serie H3 Long Video (no carga modelos, solo CPU).

    python_embeded/python.exe ComfyUI/custom_nodes/SergioNodes/selftest.py

Comprueba tres cosas:

  1. **Paridad con el nativo.** La aritmética de `h3_chunks` tiene que dar
     exactamente lo mismo que `temporal_shape` / `align_frame_count` /
     `video_latent_t` de `comfy_extras.nodes_minimax_h3`. Si ComfyUI cambia su
     rejilla, este test salta antes de que un chunk se genere con la forma
     equivocada.

  2. **La matemática de fusión.** Todas las combinaciones razonables de número de
     chunks, duraciones y solapes, comprobando las cuatro invariantes del latente
     AV: rejilla 17k+5, `latent_t % 5 == 2`, audio en `round(frames*5/3)` y
     costuras en fase.

  3. **El pipeline de nodos.** Project -> Anchor -> Vault -> Merge con un clip
     stub, comprobando que el ancla inyectada es la cola real del chunk anterior
     y que el contenido fusionado es el esperado token a token.
"""
from __future__ import annotations

UPSTREAM = None  # selftest interno original de SergioNodes para la serie H3 Long Video

import itertools
import os
import sys
import types

import torch

_PACKAGE = __name__.rsplit(".", 1)[0] if "." in __name__ else None
_HERE = os.path.dirname(os.path.abspath(__file__))

# Este pack tiene un subpaquete `nodes/` que, si su directorio aparece en sys.path,
# sombrea el módulo `nodes` raíz de ComfyUI que importa comfy_extras.nodes_minimax_h3.
# Python mete el directorio del script en sys.path[0] al ejecutarlo directamente, así
# que hay que quitarlo y poner la raíz de ComfyUI delante. En ComfyUI real esto no
# pasa (el pack se importa como paquete), pero el selftest se ejecuta fuera.
_COMFY_ROOT = os.path.dirname(os.path.dirname(_HERE))
if os.path.isdir(os.path.join(_COMFY_ROOT, "comfy_extras")):
    while _HERE in sys.path:
        sys.path.remove(_HERE)
    if _COMFY_ROOT in sys.path:
        sys.path.remove(_COMFY_ROOT)
    sys.path.insert(0, _COMFY_ROOT)

if _PACKAGE is None:      # ejecución directa: simular el paquete para los imports relativos
    _PACKAGE = "sergio_h3_selftest_pkg"
    if _PACKAGE not in sys.modules:
        _module = types.ModuleType(_PACKAGE)
        _module.__path__ = [_HERE]
        sys.modules[_PACKAGE] = _module


def _sibling(name):
    return "{}.{}".format(_PACKAGE, name)


h3_chunks = sys.modules.get(_sibling("h3_chunks"))
if h3_chunks is None:
    import importlib.util
    _spec = importlib.util.spec_from_file_location(
        _sibling("h3_chunks"), os.path.join(_HERE, "h3_chunks.py"))
    h3_chunks = importlib.util.module_from_spec(_spec)
    sys.modules[_spec.name] = h3_chunks
    _spec.loader.exec_module(h3_chunks)

H = h3_chunks

# Geometría pequeña para que el test sea rápido: 4x6 tokens por chunk.
_TEST_LATENT_H, _TEST_LATENT_W = 4, 6


class _Report:
    def __init__(self, title):
        self.title = title
        self.passed = 0
        self.failures = []

    def check(self, condition, message):
        if condition:
            self.passed += 1
        else:
            self.failures.append("[{}] {}".format(self.title, message))
        return bool(condition)

    def dump(self):
        status = "OK" if not self.failures else "{} FALLOS".format(len(self.failures))
        print("  [{}] {} comprobaciones -> {}".format(self.title, self.passed, status))
        for line in self.failures:
            print("      -", line)
        return not self.failures


# ==========================================================
# 1. Paridad con la implementación nativa
# ==========================================================
def test_native_parity() -> bool:
    report = _Report("paridad nativa")
    try:
        import comfy_extras.nodes_minimax_h3 as native
    except Exception as error:  # noqa: BLE001
        print("  [paridad nativa] OMITIDO: no se pudo importar el módulo nativo ({})".format(error))
        return True

    for frames in range(1, 3700):
        native_count, native_latent_t, native_audio_t = native.temporal_shape(frames)
        report.check(H.align_frame_count(frames) == native_count,
                     "align_frame_count({}) = {} != nativo {}".format(
                         frames, H.align_frame_count(frames), native_count))
        report.check(H.latent_t_for_frames(native_count) == native_latent_t,
                     "latent_t_for_frames({}) = {} != nativo {}".format(
                         native_count, H.latent_t_for_frames(native_count), native_latent_t))
        report.check(H.audio_t_for_frames(native_count) == native_audio_t,
                     "audio_t_for_frames({}) = {} != nativo {}".format(
                         native_count, H.audio_t_for_frames(native_count), native_audio_t))
        if report.failures:
            break

    # frames() debe ser la inversa exacta de latent_t()
    for latent_t in range(2, 2000):
        if not H.is_valid_latent_t(latent_t):
            continue
        report.check(H.latent_t_for_frames(H.frames_for_latent_t(latent_t)) == latent_t,
                     "latent_t_for_frames(frames_for_latent_t({})) != {}".format(latent_t, latent_t))
        if report.failures:
            break
    return report.dump()


# ==========================================================
# 2. Matemática de fusión
# ==========================================================
def _fake_chunk(frames, seed):
    latent_t = H.latent_t_for_frames(frames)
    audio_t = H.audio_t_for_frames(frames)
    generator = torch.Generator().manual_seed(seed)
    video = torch.randn(1, H.VIDEO_CHANNELS, latent_t, _TEST_LATENT_H, _TEST_LATENT_W, generator=generator)
    audio = torch.randn(1, H.AUDIO_CHANNELS, H.AUDIO_STREAMS, audio_t, generator=generator)
    return video, audio


def _entry(index, frames, anchor):
    return {"index": index, "frames": frames, "anchor_latent_frames": anchor}


def test_merge_math() -> bool:
    report = _Report("matematica de fusion")
    checked = 0
    seed = 0

    for count, anchor in itertools.product([1, 2, 3, 4, 5], [0, 2, 7, 12, 17]):
        for combo in itertools.combinations_with_replacement(range(0, 19, 2), count):
            for base in (0, 7, 15):
                blocks = [base + step for step in combo]
                frames_list = [H.CHUNK_HEAD + H.CHUNK_BLOCK * block for block in blocks]
                entries = [_entry(position + 1, frames, anchor)
                           for position, frames in enumerate(frames_list)]
                tensors = []
                for frames in frames_list:
                    seed += 1
                    tensors.append(_fake_chunk(frames, seed))
                videos = [item[0] for item in tensors]
                audios = [item[1] for item in tensors]

                try:
                    plan = H.plan_merge(entries)
                except ValueError as error:
                    # un ancla que el chunk no puede absorber debe fallar con mensaje claro
                    report.check("no puede absorber un ancla" in str(error),
                                 "mensaje poco claro: {}".format(error))
                    continue

                merged_video, merged_audio = H.apply_merge(videos, audios, plan)
                problems = H.validate_merged(merged_video, merged_audio, plan)
                checked += 1
                report.check(not problems,
                             "count={} anchor={} frames={} -> {}".format(count, anchor, frames_list, problems))
                if problems:
                    continue

                # El tiempo real debe coincidir con la fórmula: bloques = sum(k) - m*(N-1)
                anchor_n = H.normalize_anchor_latent_frames(anchor)
                per_join = (anchor_n - H.LATENT_HEAD) // H.LATENT_BLOCK
                expected_frames = H.CHUNK_HEAD + H.CHUNK_BLOCK * (sum(blocks) - per_join * (count - 1))
                report.check(plan["total_frames"] == expected_frames,
                             "count={} anchor={} frames={} -> total {} != {}".format(
                                 count, anchor, frames_list, plan["total_frames"], expected_frames))

    print("  [matematica de fusion] {} combinaciones".format(checked))
    return report.dump()


def test_anchor_normalisation() -> bool:
    report = _Report("normalizacion de ancla")
    # el corte seco no existe: la rejilla obliga a solapar
    report.check(H.normalize_anchor_latent_frames(0) == 2, "0 -> 2 tokens")
    report.check(H.normalize_anchor_latent_frames(1) == 2, "1 -> 2 tokens")
    report.check(H.normalize_anchor_latent_frames(2) == 2, "2 -> 2")
    report.check(H.normalize_anchor_latent_frames(7) == 7, "7 -> 7")
    report.check(H.normalize_anchor_latent_frames(6) == 7, "6 sube a 7")
    report.check(H.normalize_anchor_latent_frames(12) == 12, "12 -> 12")
    for anchor in (2, 7, 12):
        report.check(H.is_valid_anchor_latent_frames(anchor),
                     "ancla {} es válida (≡2 mod 5)".format(anchor))
        report.check(H.frames_back_for_anchor(anchor) == H.frames_for_latent_t(anchor) - 1,
                     "frames_back({}) == frames({})-1".format(anchor, anchor))
    # factibilidad
    report.check(not H.anchor_is_feasible(7, 22), "ancla 7 imposible en un chunk de 22 frames")
    report.check(H.anchor_is_feasible(7, 39), "ancla 7 posible en un chunk de 39 frames")
    report.check(H.min_frames_for_anchor(7) == 39, "ancla 7 exige 39 frames como mínimo")
    report.check(H.min_frames_for_anchor(2) == 22, "ancla 2 exige 22 frames como mínimo")
    # el mínimo declarado tiene que ser realmente el mínimo
    for anchor in (2, 7, 12, 17):
        minimum = H.min_frames_for_anchor(anchor)
        report.check(H.anchor_is_feasible(anchor, minimum),
                     "ancla {} factible justo en su mínimo ({} frames)".format(anchor, minimum))
        smaller = minimum - 1
        report.check(not H.anchor_is_feasible(anchor, smaller),
                     "ancla {} imposible con {} frames".format(anchor, smaller))
    return report.dump()


# ==========================================================
# 3. Pipeline de nodos
# ==========================================================
class _StubClip:
    def tokenize(self, prompt, minimax_ref_items=None, **kwargs):
        return {"stub": prompt}

    def encode_from_tokens_scheduled(self, tokens):
        return [[torch.zeros(1, 5120), {}]]


def _load_node(name, class_name):
    module = sys.modules.get(_sibling(name))
    if module is None:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            _sibling(name), os.path.join(_HERE, name + ".py"))
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    return getattr(module, class_name)


def test_node_pipeline() -> bool:
    report = _Report("pipeline de nodos")
    try:
        import node_helpers  # noqa: F401
    except Exception as error:  # noqa: BLE001
        print("  [pipeline de nodos] OMITIDO: node_helpers no disponible ({})".format(error))
        return True

    project_node = _load_node("minimax_h3_project", "MinimaxH3Project")
    anchor_node = _load_node("minimax_h3_anchor", "MinimaxH3ChunkAnchor")
    vault_node = _load_node("minimax_h3_vault", "MinimaxH3ChunkVault")
    merge_node = _load_node("minimax_h3_merge", "MinimaxH3MergeProject")

    project = "selftest_h3"
    directory = H.project_dir(project)
    for stale in ("project.json",):
        path = os.path.join(directory, stale)
        if os.path.isfile(path):
            os.remove(path)

    created = project_node.execute(project_name=project, create_if_missing=True, reset_index=True).result
    report.check(created[0] == project, "nombre de proyecto resuelto")
    report.check(created[2] == 1 and created[3] == 0, "proyecto empieza vacío")

    clip = _StubClip()
    for index in (1, 2, 3):
        conditioning, latent, frames_back, _ = anchor_node.execute(
            project=project, chunk_index=index, clip=clip,
            prompt="chunk {}".format(index), duration_seconds=5.0,
            width=1344, height=768, anchor_latent_frames=2,
            audio_anchor_mode="trim").result
        video, audio = H.require_h3_av_latent(latent, "selftest")
        report.check(int(video.shape[2]) == 37, "chunk {} latent_t=37".format(index))
        report.check(int(audio.shape[-1]) == 207, "chunk {} audio_t=207".format(index))

        keyframes = conditioning[0][1].get("minimax_keyframes", [])
        report.check(len(keyframes) == (0 if index == 1 else 1),
                     "chunk {} lleva {} keyframe(s)".format(index, len(keyframes)))
        if keyframes:
            keyframe = keyframes[0]
            report.check(keyframe["resolved_frame_index"] == 4,
                         "resolved_frame_index=4 en el chunk {}".format(index))
            report.check(int(keyframe["latent"].shape[2]) == 2, "ancla de 2 tokens")
            report.check("audio_latent" in keyframe, "ancla con audio")
            previous_video = H.load_chunk(directory, index - 1)[0]
            report.check(torch.equal(keyframe["latent"], previous_video[:, :, -2:]),
                         "el ancla del chunk {} es la cola real del chunk {}".format(index, index - 1))

        generator = torch.Generator().manual_seed(500 + index)
        sampled = H.build_av_latent(
            torch.randn(video.shape, generator=generator),
            torch.randn(audio.shape, generator=generator))
        saved = vault_node.execute(project=project, chunk_index=index, latent=sampled).result
        report.check(saved[1] == index + 1, "vault {} deja libre {}".format(index, index + 1))

    data = H.read_index(directory)
    report.check([entry["frames"] for entry in data["chunks"]] == [124, 124, 124],
                 "índice con 3 chunks de 124 frames")
    report.check([entry["anchor_latent_frames"] for entry in data["chunks"]] == [0, 2, 2],
                 "política de ancla registrada [0, 2, 2]")

    merged, frames, seconds, _ = merge_node.execute(
        project=project, first_index=1, last_index=0, anchor_override=-1, output_name="selftest").result
    merged_video, merged_audio = H.require_h3_av_latent(merged, "selftest")
    report.check(int(frames) == 362, "3x124 con ancla 2 -> 362 frames (el máximo entrenado)")
    report.check(int(merged_video.shape[2]) == 107, "latent_t fusionado 107")
    report.check(int(merged_audio.shape[-1]) == 603, "audio_t fusionado 603")
    report.check(abs(seconds - 15.0833) < 1e-3, "duración {:.4f}s".format(seconds))

    chunks = [H.load_chunk(directory, index) for index in (1, 2, 3)]
    expected_video = torch.cat(
        [chunks[0][0], chunks[1][0][:, :, 2:], chunks[2][0][:, :, 2:]], dim=2)
    report.check(torch.equal(merged_video, expected_video),
                 "vídeo fusionado == chunk1 + chunk2[2:] + chunk3[2:]")

    again = merge_node.execute(project=project, first_index=1, last_index=0,
                               anchor_override=-1, output_name="selftest").result[0]
    report.check(torch.equal(again["samples"].tensors[0], merged_video),
                 "la fusión es determinista")

    data = H.read_index(directory)
    for entry in data["chunks"]:
        entry["anchor_latent_frames"] = 7
    H.write_index(directory, data)
    wide = merge_node.execute(project=project, first_index=1, last_index=0,
                              anchor_override=-1, output_name="selftest").result[0]
    wide_video = wide["samples"].tensors[0]
    report.check(H.frames_for_latent_t(int(wide_video.shape[2])) == 328,
                 "con ancla 7 -> 328 frames (124*3 - 22*2)")

    # un rango con huecos debe avisar, no reventar
    H.delete_chunk(directory, 2)
    gapped = merge_node.execute(project=project, first_index=1, last_index=0,
                                anchor_override=-1, output_name="selftest").result
    report.check(int(gapped[1]) > 0, "con el chunk 2 borrado fusiona los que quedan ({} frames)".format(gapped[1]))

    for entry in list(H.list_projects()):
        if entry == project:
            import shutil
            shutil.rmtree(H.project_dir(project), ignore_errors=True)
    return report.dump()


def test_path_safety() -> bool:
    report = _Report("higiene de rutas")
    for nasty in ("../../etc/passwd", "..\\..\\windows\\system32", "a/b", "con:dos:puntos",
                  "  ", "\u0000nul", "C:\\absoluta", "x" * 500, "proyecto normal"):
        try:
            safe = H.sanitize_project_name(nasty)
            path = os.path.abspath(H.project_dir(safe, create=False))
        except ValueError:
            report.check(True, "{!r}: rechazado con mensaje claro".format(nasty[:24]))
            continue
        except Exception as error:  # noqa: BLE001
            report.check(False, "{!r}: excepcion inesperada {}".format(nasty[:24], error))
            continue
        root = os.path.abspath(H.projects_root())
        report.check(bool(safe) and path.startswith(root.rstrip(os.sep) + os.sep),
                     "{!r} -> {!r} se queda dentro del root".format(nasty[:24], safe[:28]))
    report.check(len(H.sanitize_project_name("x" * 500)) <= H.PROJECT_NAME_MAX,
                 "el nombre se recorta a {} caracteres".format(H.PROJECT_NAME_MAX))
    return report.dump()


def main() -> int:
    print("=" * 68)
    print("SergioNodes — selftest de H3 Long Video")
    print("=" * 68)
    results = [
        test_native_parity(),
        test_anchor_normalisation(),
        test_merge_math(),
        test_path_safety(),
        test_node_pipeline(),
    ]
    print("=" * 68)
    if all(results):
        print("RESULTADO: TODO CORRECTO")
        return 0
    print("RESULTADO: HAY FALLOS")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
