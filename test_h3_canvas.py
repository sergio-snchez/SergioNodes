"""Regresión del descuadre de lienzo entre chunks de MiniMax H3.

Reproduce el fallo real del 27/09/2026: el chunk 1 se guardó a 1360 px (latent W=85)
y el chunk 2 se pidió a 1368, lo que dejó el keyframe de 85 tokens frente a una
rejilla de 84 y reventó dentro del KSampler con

    RuntimeError: shape '[1, 24, 2, 1, 24, 2, 42, 2]' is invalid for input of size 195840

Comprueba que objetivo, keyframe y bloques de referencia comparten lienzo exacto.
"""

from __future__ import annotations

import os
import sys
import types
import unittest

import torch

_HERE = os.path.dirname(os.path.abspath(__file__))

# Este pack tiene un subpaquete `nodes/` que, si su directorio aparece en sys.path,
# sombrea el módulo `nodes` raíz de ComfyUI. Al ejecutarlo directamente hay que
# quitarlo y poner la raíz de ComfyUI delante (mismo truco que h3_selftest.py).
_COMFY_ROOT = os.path.dirname(os.path.dirname(_HERE))
if os.path.isdir(os.path.join(_COMFY_ROOT, "comfy_extras")):
    while _HERE in sys.path:
        sys.path.remove(_HERE)
    if _COMFY_ROOT in sys.path:
        sys.path.remove(_COMFY_ROOT)
    sys.path.insert(0, _COMFY_ROOT)

_PACKAGE = "sergio_h3_canvas_pkg"
if _PACKAGE not in sys.modules:
    _module = types.ModuleType(_PACKAGE)
    _module.__path__ = [_HERE]
    sys.modules[_PACKAGE] = _module


def _load(name):
    import importlib.util
    full = "{}.{}".format(_PACKAGE, name)
    module = sys.modules.get(full)
    if module is None:
        spec = importlib.util.spec_from_file_location(full, os.path.join(_HERE, name + ".py"))
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    return module


_native = None
_resolve = None
_frame_grid = None


def setUpModule():
    global _native, _resolve, _frame_grid
    import comfy_extras.nodes_minimax_h3 as native
    from comfy.ldm.minimax.model import _frame_grid as frame_grid
    _native = native
    _frame_grid = frame_grid
    _resolve = _load("minimax_h3_anchor")._resolve_canvas


class _StubVAE:
    """VAE que devuelve un latent con la rejilla que corresponde a los píxeles."""

    def encode(self, pixels):
        frames, height, width = pixels.shape[0], pixels.shape[1], pixels.shape[2]
        return torch.zeros(1, 24, 2, height // 16, width // 16)


class CanvasConsistency(unittest.TestCase):
    """Objetivo, keyframe y refs deben compartir la misma rejilla latente."""

    def test_real_incident_chains_at_stored_canvas(self):
        previous = {"index": 1, "width": 1360, "height": 768}
        w, h, notes = _resolve(_native, 1368, 768, previous, 2)
        self.assertEqual((w, h), (1360, 768))
        self.assertTrue(any("manda el chunk 1" in n for n in notes), notes)

    def test_keyframe_grid_matches_target_grid(self):
        previous = {"index": 1, "width": 1360, "height": 768}
        w, h, _ = _resolve(_native, 1368, 768, previous, 2)
        target_h, target_w = h // 16, w // 16
        keyframe = torch.zeros(1, 24, 2, 48, 85)       # cola real del chunk 1
        self.assertEqual(tuple(keyframe.shape[3:]), (target_h, target_w))
        # El reshape que reventaba ahora tiene que caber exacto.
        self.assertEqual(int(keyframe.numel()), 24 * 2 * target_h * target_w)

    def test_old_behaviour_would_have_crashed(self):
        """Sin la resolución de lienzo, el reshape del error no cuadra."""
        keyframe = torch.zeros(1, 24, 2, 48, 85)
        with self.assertRaises(RuntimeError):
            keyframe.reshape(1, 24, 2, 1, 24, 2, 42, 2)

    def test_first_chunk_uses_adapt_canvas(self):
        w, h, _ = _resolve(_native, 1360, 768, None, 1)
        self.assertEqual((w, h), (1344, 768))
        self.assertEqual(w % 32, 0)

    def test_references_keep_their_own_grid_and_aspect_ratio(self):
        """Las refs NO tienen que medir como el target: eso lo permite el nativo ('max' a 2048)."""
        build_refs = _load("minimax_h3_anchor")._build_refs
        w, h, _ = _resolve(_native, 1344, 768, None, 1)
        image = torch.zeros(1, 1080, 1920, 3)
        _, blocks = build_refs(_native, "match", _StubVAE(), None, 124, w, h,
                               {"ref_image_1": image}, {}, {}, {})
        self.assertEqual(len(blocks), 1)
        block = blocks[0]
        # múltiplo de 32 para que el VAE trocee, y proporción ~16:9 conservada
        self.assertEqual((block["latent_h"] * 16) % 32, 0)
        self.assertEqual((block["latent_w"] * 16) % 32, 0)
        self.assertAlmostEqual(block["latent_w"] / block["latent_h"], 1920 / 1080, delta=0.05)
        # y su rejilla es válida aunque no cuadre con la del target
        _frame_grid(block["latent_h"], block["latent_w"])

    def test_portrait_reference_is_never_stretched_to_the_canvas(self):
        """Regresión real: refs verticales (768x1360) forzadas a 1344x768 salían 3:1 de ratio.

        Con 'match' una ref vertical tiene que seguir vertical. Este test falla si alguien
        vuelve a forzar las referencias al lienzo del target.
        """
        build_refs = _load("minimax_h3_anchor")._build_refs
        w, h, _ = _resolve(_native, 1344, 768, None, 1)
        portrait = torch.zeros(1, 1360, 768, 3)
        _, blocks = build_refs(_native, "match", _StubVAE(), None, 124, w, h,
                               {"ref_image_1": portrait}, {}, {}, {})
        block = blocks[0]
        self.assertLess(block["latent_w"], block["latent_h"], "la ref vertical se ha tendido")
        self.assertAlmostEqual(block["latent_w"] / block["latent_h"], 768 / 1360, delta=0.05)
        _frame_grid(block["latent_h"], block["latent_w"])

    def test_reference_at_odd_latent_width_is_still_valid(self):
        """El ref puede caer en latent impar: _frame_grid es inmune a la paridad."""
        build_refs = _load("minimax_h3_anchor")._build_refs
        w, h, _ = _resolve(_native, 1344, 768, None, 1)
        image = torch.zeros(1, 768, 1360, 3)           # 1360//32*32 = 1344 -> par
        _, blocks = build_refs(_native, "match", _StubVAE(), None, 124, w, h,
                               {"ref_image_1": image}, {}, {}, {})
        _frame_grid(blocks[0]["latent_h"], blocks[0]["latent_w"])
        self.assertEqual(blocks[0]["latent_w"], 84)

    def test_bankers_rounding_is_the_original_offender(self):
        """round(42.5) == 42 en Python: por eso 1360 se quedaba en 1344."""
        self.assertEqual(round(1360 / 32) * 32, 1344)
        self.assertNotEqual(round(1360 / 32) * 32, 1360)

    def test_odd_latent_width_is_what_breaks_patchify(self):
        """85//2 == 42: patchify_video se come una columna y el reshape no cuadra."""
        odd = torch.zeros(1, 24, 2, 48, 85)
        pt, ph, pw = 1, 2, 2
        t, h, w = odd.shape[2] // pt, odd.shape[3] // ph, odd.shape[4] // pw
        with self.assertRaises(RuntimeError):
            odd.reshape(1, 24, t, pt, h, ph, w, pw)

    def test_keyframe_is_padded_to_the_patch_grid(self):
        pad_to_patch = _load("minimax_h3_anchor")._pad_to_patch
        odd = torch.zeros(1, 24, 2, 48, 85)
        padded = pad_to_patch(odd)
        self.assertEqual(tuple(padded.shape[3:]), (48, 86))
        # ya parchea sin errores
        t, h, w = padded.shape[2], padded.shape[3] // 2, padded.shape[4] // 2
        self.assertEqual(int(padded.numel()), 1 * 24 * t * 1 * h * 2 * w * 2)
        padded.reshape(1, 24, t, 1, h, 2, w, 2)

    def test_even_latent_needs_no_padding(self):
        pad_to_patch = _load("minimax_h3_anchor")._pad_to_patch
        even = torch.zeros(1, 24, 2, 48, 84)
        self.assertIs(pad_to_patch(even), even)

    def test_padded_keyframe_matches_padded_video_latent(self):
        """El DiT rellena el latent principal; el keyframe debe acabar igual de ancho."""
        pad_to_patch = _load("minimax_h3_anchor")._pad_to_patch
        main = torch.zeros(1, 24, 107, 48, 85)
        keyframe = torch.zeros(1, 24, 2, 48, 85)
        _, _, pw = 1, 2, 2

        main_p = pad_to_patch(main)
        key_p = pad_to_patch(keyframe)
        self.assertEqual(int(main_p.shape[4]), int(key_p.shape[4]))
        self.assertEqual(int(main_p.shape[3]), int(key_p.shape[3]))
        # y el patchify del keyframe entra en la rejilla del video
        self.assertEqual(key_p.shape[4] // pw, main_p.shape[4] // pw)

    def test_rejects_canvas_not_divisible_by_16(self):
        with self.assertRaises(ValueError):
            _resolve(_native, 1000, 768, {"width": 1000, "height": 768}, 2)

    def test_odd_latent_canvas_is_accepted_but_warned(self):
        """1360 -> latent 85: funciona con relleno, pero se avisa de la columna inventada."""
        w, h, notes = _resolve(_native, 1360, 768, None, 1)
        self.assertEqual((w, h), (1344, 768))          # chunk 1 pasa por adapt_canvas
        odd = {"width": 1360, "height": 768}
        w, h, notes = _resolve(_native, 1360, 768, odd, 2)
        self.assertEqual((w, h), (1360, 768))
        self.assertTrue(any("no es múltiplo de 32" in n for n in notes), notes)

    def test_empty_av_latent_is_a_dict_not_a_tensor(self):
        """El anchor comparaba latent.shape y petaba con AttributeError al encadenar."""
        video_tensor = _load("minimax_h3_anchor")._video_tensor
        latent, frames = _native._empty_av_latent(1344, 768, 362)
        self.assertIsInstance(latent, dict)
        self.assertEqual(int(frames), 362)
        video = video_tensor(latent)
        self.assertEqual(tuple(video.shape[3:]), (48, 84))
        # y un tensor pelado también se resuelve
        self.assertIs(video_tensor(video), video)

    def test_canonical_canvas_emits_no_warning(self):
        w, h, notes = _resolve(_native, 1344, 768, None, 1)
        self.assertEqual((w, h), (1344, 768))
        self.assertFalse(any("múltiplo de 32" in n for n in notes), notes)

    def test_missing_previous_chunk_falls_back_to_widget(self):
        w, h, _ = _resolve(_native, 1344, 768, None, 3)
        self.assertEqual((w, h), (1344, 768))

    def test_chain_is_stable_across_three_chunks(self):
        previous = {"index": 1, "width": 1360, "height": 768}
        w2, h2, _ = _resolve(_native, 1368, 768, previous, 2)
        previous2 = {"index": 2, "width": w2, "height": h2}
        w3, h3, _ = _resolve(_native, 1600, 900, previous2, 3)
        self.assertEqual((w2, h2), (w3, h3))


if __name__ == "__main__":
    unittest.main(verbosity=2)
