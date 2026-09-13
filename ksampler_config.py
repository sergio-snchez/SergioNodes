import comfy.samplers
from nodes import MAX_RESOLUTION


class KSamplerConfig:
    """Sin dependencias externas. Clon del KSampler Config de rgthree."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "seed": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 0xffffffffffffffff,
                    "control_after_generate": True,
                }),
                "steps_total": ("INT", {
                    "default": 30,
                    "min": 1,
                    "max": MAX_RESOLUTION,
                    "step": 1,
                }),
                "refiner_step": ("INT", {
                    "default": 24,
                    "min": 1,
                    "max": MAX_RESOLUTION,
                    "step": 1,
                }),
                "cfg": ("FLOAT", {
                    "default": 8.0,
                    "min": 0.0,
                    "max": 100.0,
                    "step": 0.5,
                }),
                "sampler_name": (comfy.samplers.KSampler.SAMPLERS,),
                "scheduler": (comfy.samplers.KSampler.SCHEDULERS,),
            },
        }

    RETURN_TYPES = ("INT", "INT", "INT", "FLOAT", comfy.samplers.KSampler.SAMPLERS,
                    comfy.samplers.KSampler.SCHEDULERS)
    RETURN_NAMES = ("SEED", "STEPS", "REFINER_STEP", "CFG", "SAMPLER", "SCHEDULER")
    FUNCTION = "main"
    CATEGORY = "Sergio Nodes"

    def main(self, seed, steps_total, refiner_step, cfg, sampler_name, scheduler):
        return (
            seed,
            steps_total,
            refiner_step,
            cfg,
            sampler_name,
            scheduler,
        )


NODE_CLASS_MAPPINGS = {"KSampler_Config": KSamplerConfig}
NODE_DISPLAY_NAME_MAPPINGS = {"KSampler_Config": "KSampler Config"}