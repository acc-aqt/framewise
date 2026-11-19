# Writing a Provider

framewise analyzes each Frame's Analysis source with one Provider per Capability. You can add a Provider for any Capability from your own Python package, without changing framewise. The reasons behind this design are in [ADR-0005](adr/0005-pluggable-analysis-providers.md).

## Capabilities

| Capability | Method | Returns |
|---|---|---|
| `fingerprint` | `fingerprint(jpg_path)` | A list of floats. Frames whose fingerprints are similar form Groups. |
| `face-detection` | `detect_faces(jpg_path)` | One box per face. |
| `eye-state` | `eyes_open(jpg_path, faces)` | For each box, `True` (open), `False` (closed) or `None` (cannot tell). |
| `face-quality` | `face_quality(jpg_path, faces)` | For each box, a score from 0 to 1, or `None`. |
| `expression` | `expression(jpg_path, faces)` | For each box, an `Expression`, or `None` (cannot read the face). |
| `aesthetics` | `aesthetics(jpg_path)` | A score from 0 to 1, or `None`. |
| `subject` | `subject_mask(jpg_path)` | A mask of the Frame's main subject, or `None` where it finds none. |

The protocols are in `backend/src/framewise/providers.py`. `jpg_path` is a `pathlib.Path` to the Frame's JPG.

- **fingerprint** is the only Capability framewise cannot run without, because it groups Frames by it.
- Without a Provider for any other Capability, its signals are simply unknown: a Frame has no faces, or its eyes and scores are unknown. Judging treats unknown signals as unknown, never as a flaw.

### Boxes

A box is a tuple `(x, y, width, height)`:

- measured as fractions from 0 to 1 of the Frame as it is displayed, after its EXIF orientation;
- measured from the top left.

The face detection Provider alone decides which faces a Frame has. The eye state, face quality and expression Providers receive its boxes, possibly from a different Provider, and must return exactly one value per box, in the same order. framewise leaves out faces too small to measure.

### Expressions

`Expression`, from `framewise.analyzer`, holds what an expression Provider reads from a face:

- `smile`: from 0 for a neutral or downturned mouth to 1 for a broad smile.
- `looking`: from 0 for eyes looking fully aside to 1 for eyes looking into the lens.
- `facing`: from 0 for a head turned fully away to 1 for a head facing the camera.

framewise's MediaPipe Provider reads `looking` relative to the head, not the camera: a head turned away whose eyes look back into the lens scores low on both `looking` and `facing`.

Leave any part your Provider cannot tell as `None`; `looking` and `facing` default to it. framewise weighs the parts a face has into one expression, the smile 0.4 and the other two 0.3 each, and ranks a Frame by its weakest face's expression. Expression never counts as a flaw.

### Subject masks

A subject mask is a greyscale `PIL.Image.Image` (mode `"L"`):

- covering the Frame as it is displayed, after its EXIF orientation, at any size: framewise stretches it over the Frame;
- 255 inside the subject and 0 outside it.

framewise measures sharpness on the mask's pixels alone, shrunk by a few pixels so the subject's outline against the background doesn't count. A Frame without faces is judged on that sharpness, unless its camera recorded a focus point, which wins. framewise ignores a mask too small to measure.

### Scales

Return face quality, smiles and aesthetics on the 0 to 1 scale, whatever your model's own scale is. Any threshold your Provider applies, such as the openness below which eyes count as closed, is yours to choose and calibrate.

### Similarity thresholds

A fingerprint Provider declares how similar two fingerprints must be, by cosine similarity, for two Frames to share a Group:

```python
similarity = SimilarityThresholds(burst=0.8, near_duplicate=0.9)
```

- `burst` applies to Frames taken up to 2 seconds apart.
- `near_duplicate` applies to Frames taken up to 5 minutes apart, or whose capture time is unknown.

Calibrate them for your model. Thresholds from another model mean nothing for yours.

## Every Provider

Besides its Capability's method, a Provider has:

| Attribute | Meaning |
|---|---|
| `capability` | One of the Capability names above. |
| `id` | A stable, unique name such as `"acme-eye-state"`. Saved analyses record it, and `config.toml` chooses by it. Never change it. |
| `version` | An integer. Bump it whenever your Provider's output may change, such as a new model or threshold. framewise then analyzes the Frames your old version analyzed again. |
| `priority` | An integer. By default each Capability uses its highest-priority available Provider. framewise's Apple Vision Providers use 100 and its portable ones (MediaPipe and DINOv2) 50. |
| `is_available()` | Whether the Provider can run on this machine, for example whether its dependencies and models are present. It must never raise. A Provider whose check raises is treated as unavailable. |

framewise may call a Provider from several threads at once, one Frame per thread.

## Registering

Register your Provider in the `framewise.providers` entry-point group of your package. Each entry point names a class, or a function, that framewise calls with no arguments:

```toml
[project.entry-points."framewise.providers"]
acme-eye-state = "acme_framewise:AcmeEyeState"
```

```python
from pathlib import Path

from framewise.providers import EYE_STATE


class AcmeEyeState:
    capability = EYE_STATE
    id = "acme-eye-state"
    version = 1
    priority = 10

    def is_available(self) -> bool:
        return True

    def eyes_open(self, jpg_path: Path, faces: list) -> list[bool | None]:
        return [None for _ in faces]
```

Install your package into the same environment as framewise. An entry point that fails to load is skipped with a warning, so a broken plug-in never stops framewise.

## Choosing Providers

To use a Provider other than the highest-priority one, name its id in the `[providers]` table of `config.toml`, in the same folder as the Session stores (`~/Library/Application Support/framewise/` on macOS, `~/.local/share/framewise/` on Linux by default):

```toml
[providers]
eye-state = "acme-eye-state"
```

A Provider named here that is not installed or not available on the machine stops framewise with an error. framewise never falls back to another Provider silently.

## Benchmarking a Provider

`framewise-benchmark` measures how often the Proposal agrees with the photographer's Reference ratings in Lightroom Classic. Run it once with the default Providers and once with yours:

```bash
uv run framewise-benchmark /path/to/session --report default.json
uv run framewise-benchmark /path/to/session --provider eye-state=acme-eye-state --report acme.json
```

`--provider <capability>=<id>` can be repeated and wins over `config.toml`. Each report lists the Provider that served each Capability, the agreement figures and the time analysis took.

## Testing

`backend/tests/test_providers.py` composes analysis from fake Providers and is a good model for testing yours.
