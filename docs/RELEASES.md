# Nexus releases and provenance

## Version control history

Development from 0.1.9 (commit `f4d791b`) to 0.1.14 was not committed as it happened. Intermediate versions have no history and none was reconstructed. Commits and tags carry their true creation date, which is after deployment.

## 0.1.15

| | |
| --- | --- |
| Tag | `v0.1.15` (annotated, tag object `3b154ca6536fb713fdb1369532fe9ff90f81eb25`) |
| Release commit | `e54e76d61faec8e7b1f64c772d4384be562760dc`, created 2026-11-09 before any deployment |
| Release image | `sha256:c425c461966df833929461b004bd35fd4a18ce7afd914bfa9f12f074c652b69a`, built from a clean clone of this commit |
| Image built | 2026-11-09T18:14:43.812671624Z |
| Deployed | **Not deployed to Exodus.** This image runs on aetest |
| CI | GitHub Actions run 42672124578 passed on this commit, every step (second attempt; the first started no jobs) |

### What has been demonstrated

Checked on 2026-11-09. Evidence is in `VALIDATION_P1_NAVIGATION_AETEST_2026-11-09.md` at the workspace root.

- All 24 files under the image's `/app/backend` and `/app/frontend` are byte-identical to this commit.
- Against the working-tree build first validated on aetest, those files match except for line endings: 4 byte-identical and 20 differing only in line endings.
- This exact image was then installed on aetest, and the universal navigation journeys passed against it in Chromium, WebKit and Firefox on Linux.
- The unit suite passes on the clean clone: 230 passed, 1 skipped; frontend 31 passed.

### What has not been demonstrated

- The build is **not reproducible to the digest**. Rebuilds of unchanged source gave different image IDs.
- Physical mouse buttons, native keyboard shortcuts, Safari and real phones have not been checked.
- It has not run in production.

## 0.1.14

| | |
| --- | --- |
| Tag | `v0.1.14` (annotated, tag object `1b4b5a28e8fbead7caded78547cc9b39280af52c`) |
| Baseline commit | `64865656ef775f76bf8bfecbee437c29de98ad2e`, created 2026-11-09 after deployment |
| Deployed image | `sha256:e8e71af28c91bad10c55ed2e54a184f0e7e2f54496ad6867932763ee5d54b6ec` |
| Image config | `sha256:05b277ae9f6ea7bc6c388905912319a04fe5c9cffcb59393b1a399e1b5f801b8` |
| Image built | 2026-11-09T08:22:01.058785621Z |
| Deployed | Exodus, 2026-11-09. The running container's image was read back on 2026-11-09 and matches the digest above |

### What has been demonstrated

Checked on 2026-11-09 from a clean clone of the tagged commit, against the image archive saved at release time.

- Of 31 non-compiled files in the image's `/app`, 4 are byte-identical to the tag and 26 differ only in line endings, and 1 differs as described below.
- The image was rebuilt with `deploy/Dockerfile`. Every file outside `/app` that is not a compiled `.pyc` is identical. Entrypoint, environment and user are the same.
- The unit suite passes on the clone: 230 passed, 1 skipped.

### What has not been demonstrated

The build is **not reproducible to the digest**. Two rebuilds gave two different digests, sharing 5 of 13 layers with the deployed image.

- `README.md`, copied into the image, differs by one status line: the image says the source tree is 0.1.13 and the tag says 0.1.14. The line was updated at 09:47, after the image was built at 09:22 local time. It has no runtime effect.
- The deployed image was built from a Windows working tree, so 26 text files have CRLF line endings there and LF here.
- 653 `.pyc` files from installed packages differ between builds, because they embed build-time data.
- The commit was made after the image was built. It records matching content, not the build's actual input.

## Conventions

Create the tag before deploying and build from a clean checkout of it. Record the commit and image digest in the deployment record. Do not move a published tag.
