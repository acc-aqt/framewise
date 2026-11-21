# ADR-0005: Pluggable analysis Providers

**Status:** Accepted — 2026-11-14. Amended — 2026-11-20: the subject Capability and the Focus point reader (§1, §5, §8).

## Context

Tier 1 analysis (ADR-0002) was written directly against Apple Vision, so framewise only ran on macOS and nobody could try a different face detector, eye-state check or fingerprint without editing framewise. Developers want to plug in other tools, the photographer wants framewise on Linux, and a swap must never quietly mix results from two different tools in one Session.

## Decision

1. **Analysis is split into Capabilities, each served by one Provider.**
   - The Capabilities are fingerprint, face detection, eye state, face quality, aesthetics and subject.
   - Face detection alone decides which faces a Frame has. Eye state and face quality get its boxes and judge only those faces.
2. **Providers are found through the `framewise.providers` entry-point group.**
   - framewise's own Providers are registered the same way as a plug-in's.
   - A Provider that fails to load, or whose availability check raises, is skipped with a warning, so a broken plug-in cannot stop framewise.
3. **Each Capability uses its highest-priority available Provider,** unless the photographer chooses one.
   - The choice is made in the `[providers]` table of `config.toml` beside the Session stores, or with `--provider` on the benchmark, which wins over the file.
   - A chosen Provider that is not installed or not available on the machine is an error, never a silent fallback to another Provider.
4. **Fingerprint is the only mandatory Capability.** Without it Frames cannot be grouped, so framewise refuses to start. Without any other Capability, its signals are unknown (no faces, unknown eyes, no face quality or aesthetics score), and judging treats them as unknown rather than as a flaw.
5. **The image maths stays built in.** Sharpness, motion blur, exposure, whether a Frame is deliberately low or high key, per-face sharpness inside the detected boxes and the Subject's sharpness inside the Focus point or the subject Provider's mask are computed by framewise for every Provider, so they are the same whichever Providers run.
6. **Providers own their calibration.**
   - A fingerprint Provider declares its own similarity thresholds for bursts and near-duplicates, because fingerprints from different models are not comparable.
   - Face quality and aesthetics are scores from 0 to 1. A Provider maps its model's own scale onto that range and keeps any threshold, such as for closed eyes, to itself.
7. **Provider signatures drive re-analysis.**
   - Each saved analysis records which Provider, and which version of it, served each Capability.
   - A Frame whose recorded Providers differ from the current ones is analyzed again. Until then it is left out of Groups, so fingerprints from two Providers are never compared.
   - The analysis version now covers only the built-in image maths and the shape of the saved signals. A Provider signals a change in its output by bumping its own version.
8. **The Focus point is read by framewise itself, not by a Provider.**
   - framewise reads it from the maker notes of the Analysis source with ExifTool, which it already needs for Rating write-back, and it wins over the subject Provider's mask.
   - It is a fact the camera recorded, not a judgment a model makes, so there is nothing to swap: reading it depends on the camera brand, not on an analysis tool, and every reader would return the same area.
   - It still appears in the Provider signature, so a Frame analyzed without ExifTool is analyzed again once ExifTool is installed.

## Considered Options

- **Plugging in a whole analyzer** instead of one Provider per Capability. Rejected: every plug-in would re-implement the image maths, and one could not combine, say, Apple Vision fingerprints with another eye-state check.
- **Platform checks inside framewise** choosing Apple Vision or something else. Rejected: every new tool would mean editing framewise.
- **Falling back to the default when a chosen Provider is unavailable.** Rejected: the photographer would get different Verdicts without knowing why.
- **Reading the Focus point in a subject Provider.** Rejected: choosing another subject Provider would lose the Focus point, and every subject Provider would have to parse maker notes again.

## Consequences

- Changing any Provider, even one that has nothing to do with grouping such as eye state, empties the Proposal and the Groups, fixed ones included, until the affected Frames are analyzed again. This is the same as bumping the analysis version.
- framewise runs on Linux with the portable Providers of the `portable` extra: DINOv2-small serves the fingerprint, with similarity thresholds calibrated so its Groups match Apple Vision's on a benchmark Session, and MediaPipe serves face detection and eye state. Linux has no face quality, aesthetics or subject Provider yet.
- Providers in one package may share work between themselves. framewise's Apple Vision Providers share one Vision image per thread, so face detection's observations are reused by eye state and face quality. That sharing is a Provider's own business and not part of the Provider protocol.
- A plug-in author's guide lives in `docs/providers.md`.
