import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from PIL import Image, ImageDraw

MODULE_PATH = Path(__file__).parents[1] / "sprite_forge" / "sprite_forge.py"
SPEC = importlib.util.spec_from_file_location("sprite_forge", MODULE_PATH)
forge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(forge)


class SpriteForgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        source = Image.new("RGBA", (80, 40), (0, 0, 0, 0))
        draw = ImageDraw.Draw(source)
        draw.ellipse((3, 3, 29, 29), fill=(220, 70, 20, 255))
        draw.rectangle((8, 24, 25, 35), fill=(45, 25, 15, 255))
        draw.ellipse((43, 3, 69, 29), fill=(220, 70, 20, 255))
        draw.rectangle((48, 24, 65, 35), fill=(45, 25, 15, 255))
        source.save(self.root / "source.png")
        manifest = {
            "asset": "test_ant",
            "frame_size": [64, 64],
            "columns": 2,
            "animations": [{
                "name": "walk", "fps": 8, "loop": True,
                "layout": {"padding": 4, "anchor": "bottom_center"},
                "frames": [
                    {"source": "source.png", "rect": [0, 0, 40, 40]},
                    {"source": "source.png", "rect": [40, 0, 40, 40]}
                ]
            }]
        }
        (self.root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        self.manifest = self.root / "manifest.json"

    def tearDown(self):
        self.temp.cleanup()

    def test_inspect_reports_real_alpha(self):
        info = forge.inspect_image(self.root / "source.png")
        self.assertTrue(info["has_alpha_band"])
        self.assertGreater(info["transparent_pixels"], 0)

    def test_assemble_and_validate(self):
        output = self.root / "build"
        result = forge.command_assemble(SimpleNamespace(manifest=str(self.manifest), output=str(output)))
        self.assertEqual(result, 0)
        atlas = output / "atlas" / "test_ant_atlas.png"
        metadata = output / "atlas" / "test_ant_frames.json"
        with Image.open(atlas) as image:
            self.assertEqual(image.size, (128, 64))
            self.assertEqual(image.mode, "RGBA")
        self.assertEqual(forge.command_validate(SimpleNamespace(atlas=str(atlas), manifest=str(metadata))), 0)

    def test_godot_resource_uses_atlas_regions(self):
        output = self.root / "build"
        forge.command_assemble(SimpleNamespace(manifest=str(self.manifest), output=str(output)))
        atlas = output / "atlas" / "test_ant_atlas.png"
        metadata = output / "atlas" / "test_ant_frames.json"
        resource = output / "atlas" / "test_ant_frames.tres"
        forge.command_godot(SimpleNamespace(
            atlas=str(atlas), manifest=str(metadata),
            texture_path="res://assets/enemies/test_ant_atlas.png",
            output=str(resource)
        ))
        text = resource.read_text(encoding="utf-8")
        self.assertIn('type="SpriteFrames"', text)
        self.assertIn('region = Rect2(64, 0, 64, 64)', text)
        self.assertIn('&"walk"', text)


if __name__ == "__main__":
    unittest.main()
