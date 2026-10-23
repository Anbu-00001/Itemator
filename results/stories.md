# Real pull requests, and what the card would have said

In each of the 24 real cases on [the cases page](real_catches.md), a reviewer commented on the file by hand. The median wait from the pull request opening (not from the commit that added the file, which the README counts from) to that comment was 4.5 hours; 5 waited more than a day ([timing](catch_timing_v1.json)). Each story below is the longest wait in its outcome, among the comments that ask to take out the whole file (the rule and its history are in eval/stories_page.py). Nobody saw an Itemator card on these pull requests. One more case, an install script Copilot added, was replayed with the real job and flows: [second-project !2](https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/39194174/second-project/-/merge_requests/2).

No story for: merged (or still open) with the file in it. No comment there that asks to take a file out is about the whole file, so a story would put an objection next to an extra it was not about. The first version of the rule did that, with a licence line in Azure/azure-sdk-for-python#42404.

### Copilot in vllm-project/semantic-router: `TRACING_FEATURE.md`

Copilot opened [the pull request](https://github.com/vllm-project/semantic-router/pull/322). What the rules list in `TRACING_FEATURE.md`: Adds a top-level document the issue does not name; the issue does not ask for it. A reviewer wrote ["@copilot this file is not needed"](https://github.com/vllm-project/semantic-router/pull/322#discussion_r2402051904) 15.1 hours after the pull request opened. The file was taken out of the pull request.

**With Itemator:** the card would have named it when the pipeline finished, and the merge request would have stayed a draft until someone kept it, split it or removed it.

### Copilot in microsoft/react-native-windows: `rnwcoreJSI-generated.cpp`

Copilot opened [the pull request](https://github.com/microsoft/react-native-windows/pull/14796). What the rules list in `rnwcoreJSI-generated.cpp`: 3 files whose changes are whitespace only (indentation, blank lines or the final newline). A reviewer wrote ["remove changes in this file.. not needed this file should not be there in files changed for this pr"](https://github.com/microsoft/react-native-windows/pull/14796#discussion_r2153757091) 6.5 hours after the pull request opened. The pull request was closed without merging.

**With Itemator:** the card would have named it when the pipeline finished, and the merge request would have stayed a draft until someone kept it, split it or removed it.
