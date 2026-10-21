// The task text for the other checker, the same as Itemator's head-to-head gave it: the issues this merge request
// closes (title and description), else the merge request's own title and description. Public API, read-only.
const api = process.env.CI_API_V4_URL, pid = process.env.CI_PROJECT_ID, iid = process.env.CI_MERGE_REQUEST_IID;
let text = "";
try {
  const r = await fetch(`${api}/projects/${pid}/merge_requests/${iid}/closes_issues`);
  const issues = r.ok ? await r.json() : [];
  text = issues.map((i) => `${i.title}\n${i.description || ""}`).join("\n\n");
} catch (e) { /* fall back below */ }
if (!text.trim()) text = `${process.env.CI_MERGE_REQUEST_TITLE || ""}\n${process.env.CI_MERGE_REQUEST_DESCRIPTION || ""}`;
process.stdout.write(text);
