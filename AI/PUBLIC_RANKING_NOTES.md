# Public Ranking Notes

LACA v0.8.1 uses a simple BM25F-style field ranking baseline.

The ranking fields are:

- filename
- path
- headings
- content preview
- status evidence

The tokenizer is Unicode-aware and supports Ukrainian/Cyrillic text, Latin text, numbers, and mixed-language identifiers.

This public version intentionally uses simple terminology: project map, task spec, action points, continue mode, result history, and change log.
