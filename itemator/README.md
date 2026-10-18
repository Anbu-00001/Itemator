# itemator/

`extras.py` holds the rules the CI job runs (version 6). `extras_v1.py` to `extras_v5.py` are earlier versions kept unchanged on purpose: each study in `results/` names the rules version it ran, and re-running an old study needs the exact rules it used. Nothing imports them in the CI job. `neutral.py`, `unwrap.py`, `cochange.py` and `trace.py` are separate checks that need no issue text; `local.py` is the command that runs the rules on your own machine.
