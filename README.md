# Sprite Forge

A reusable toolkit for turning approved character and object artwork into consistent sprite frames, atlases, previews, and engine resources.

Sprite Forge separates art creation from technical assembly: artists and image generators create source art; Sprite Forge inspects, extracts, aligns, assembles, validates, previews, and packages it.

## Requirements

- Python 3.10+
- Pillow 10+

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

## Quick start

Inspect source artwork:

```bash
python -m sprite_forge inspect path/to/source.png
```

Extract source rectangles:

```bash
python -m sprite_forge extract manifests/example_manifest.json --output build/source_frames
```

Assemble normalized frames and a transparent atlas:

```bash
python -m sprite_forge assemble manifests/example_manifest.json --output build/example
```

Validate the atlas:

```bash
python -m sprite_forge validate build/example/atlas/example_enemy_atlas.png build/example/atlas/example_enemy_frames.json
```

Create a contact sheet:

```bash
python -m sprite_forge preview manifests/example_manifest.json --output build/example/contact_sheet.png
```

Package output:

```bash
python -m sprite_forge package build/example --output build/example_review.zip
```

Generate a Godot 4 SpriteFrames resource:

```bash
python -m sprite_forge godot-resource build/example/atlas/example_enemy_atlas.png build/example/atlas/example_enemy_frames.json --texture-path res://assets/example_enemy_atlas.png --output build/example/atlas/example_enemy_frames.tres
```

## Commands

| Command | Purpose |
|---|---|
| `inspect` | Report dimensions, color mode, and alpha-channel statistics |
| `extract` | Extract explicitly defined source rectangles |
| `assemble` | Normalize frames and assemble a transparent atlas |
| `validate` | Check atlas dimensions, regions, alpha, and duplicate frames |
| `preview` | Generate a labeled contact sheet |
| `package` | Create and verify a ZIP archive |
| `godot-resource` | Export a Godot 4 SpriteFrames resource |

## Manifest format

See [manifests/example_manifest.json](manifests/example_manifest.json). Source paths are relative to the manifest. Each frame uses an explicit crop rectangle `[x, y, width, height]`; Sprite Forge does not guess crop boundaries.

Top-level `frame_size` is `[width, height]`; `columns` controls atlas columns. Animations are packed in manifest order. Each animation may set `fps`, `loop`, and layout options:

- `padding`: integer or `[left, top, right, bottom]`
- `anchor`: `bottom_center`, `center`, or normalized `[x, y]`
- `resample`: `nearest` or `lanczos`

## Output

- `frames/<animation>/<NN>.png`: normalized individual frames
- `atlas/<asset>_atlas.png`: transparent RGBA atlas
- `atlas/<asset>_frames.json`: atlas regions and animation metadata

## Design principles and limitations

- Source images are never modified.
- Crop rectangles are explicit and reproducible.
- Background removal is intentionally not automatic; color-key removal can destroy dark outlines and antialiased edges.
- Missing animation poses are never invented. Duplicate frames are reported as warnings, not silently removed.
- Validation checks technical structure, alpha, frame counts, and regions; it cannot judge animation quality. Review previews and test at in-game scale.
- The Godot resource exporter writes a `.tres` file but does not launch Godot to verify import settings or texture paths.

## Development

Run tests from the repository root:

```bash
python -m unittest discover -s tests -v
```

## Provenance

The initial implementation was developed for Backyard Heroes and is being extracted into this standalone repository for reuse across projects. This first standalone port preserves the original image-processing workflow and Godot exporter. Additional engine exporters will be added as separately tested modules.

## License

Sprite Forge is licensed under the [MIT License](LICENSE). You may use, modify, distribute, sublicense, and sell copies of the software, provided the copyright and license notice are included. The license is permissive and does not require derivative projects to publish their source code.
