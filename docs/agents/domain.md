# Domain docs

framewise keeps its domain language in [`GLOSSARY.md`](../../GLOSSARY.md) and its decisions in [`docs/adr/`](../adr/). Read both before exploring the code: the Glossary in full, and the ADRs that touch the area you're working in.

## Use the Glossary's terms

When you name a domain concept (in an issue title, a proposal, a test name), use the Glossary term, and don't drift to the synonyms it lists under _Avoid_. For example, write Frame, not photo or image.

If a concept you need isn't in the Glossary, either you're inventing language the project doesn't use (reconsider) or there's a real gap (note it for `/domain-modeling`, which maintains the Glossary and ADRs).

## Flag ADR conflicts

If your work contradicts an ADR, say so explicitly instead of silently overriding it:

> _Contradicts ADR-0003 (Overrides), but worth reopening because…_
