# Reviewed CMS base transition

The release baseline `2f430442387b2db6277f0e7c29f7c33327e8e35c` and
`f78b7bd3c38d6f19168a9d6fe38994af761ecc1e` have identical CMS files,
lockfiles, and release build scripts apart from the three base-selection files
listed in `automatic-release-adapter.py`. The reconstruction change selects a
domestic mirror first and falls back to an official source with the same pinned
Node and PostgreSQL manifest digests. PostgreSQL is an integration-test input,
not the production CMS image. Both paths check platform and PostgreSQL user.

On 2026-11-15, the old and new Node reconstruction Dockerfiles were built
locally without network access, with the same locally cached pinned Node parent
and the Node binary verified against the reconstruction script's SHA-256
`94efd062ed066c1a0b332e18249859c905e920eeada5df55d24c99b919629a90`.
Docker inspection reported identical root filesystem diff IDs and runtime
configuration. The image IDs differed, so this is not a claim of byte-identical
OCI manifests or identical build metadata. The new exact release image passed
the hosted integration suite in run 43661303086.

This supports the narrow rollback compatibility decision for this transition;
it does not prove safety for CMS schema changes or arbitrary future base
reconstructions. The controller requires the exact baseline, a descendant of
the reviewed transition, precisely these changed paths and exact Git blobs;
it retains all live-image, signed-artifact and health checks. Any additional
CMS input change remains a hard stop.
