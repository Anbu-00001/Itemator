# Itemator

**One click for what was asked. A name for anything more.**

When an agent or a new teammate opens a merge request, someone approves it, often without reading. Itemator lists what the change did beyond its linked issue. A GitLab Duo flow offers to move each extra into its own merge request, and the approver keeps an extra only by typing its name. Changes that stay inside the issue keep the normal one-click approval.

**Status:** in development for GitLab's *Life After Code* hackathon (Path A, Supervised). Nothing below this line is a result yet; results will link to the script and data that produced them.

## Why Python
We checked whether Itemator should be written in Rust, Go, TypeScript or C++ instead. We kept Python, because speed is not the problem and a rewrite would cost most of our remaining time for no change in any result. The full reasoning, with numbers that trace to files, is in [docs/why-python.md](docs/why-python.md).

## Licence
MIT. See [LICENSE](LICENSE). The evaluation uses the AIDev dataset (CC BY 4.0), fetched by script and not redistributed; see [NOTICE](NOTICE).
