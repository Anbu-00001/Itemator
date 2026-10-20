# Running the checks on Google Cloud Run

`itemator/serve.py` is the same added-line checks (moving, shapes, untrusted text) behind one HTTP address: `POST` a git diff to `/check`, get the findings as JSON. It stores nothing, logs no request, accepts a body only up to the size set as `MAX_BODY` in the file, and answers `GET /` with what it is. The `deploy-cloud-run` job in `.gitlab-ci.yml` deploys it by hand, with a short-lived Workload Identity Federation token (no key file), one instance at most, twenty requests at once, a ten-second request.

The job appears in the pipeline only when these project CI/CD variables exist (none of them is a secret):

| Variable | Value |
|---|---|
| `GCP_PROJECT_ID` | the Google Cloud project id |
| `GCP_WIF_AUDIENCE` | `//iam.googleapis.com/projects/<number>/locations/global/workloadIdentityPools/<pool>/providers/<provider>` |
| `GCP_SERVICE_ACCOUNT` | the service account email that may deploy |

Set-up, once (a few hours for a first-timer): create a project and attach a billing account (a free trial is enough), enable the Cloud Run, Cloud Build, Artifact Registry and IAM Credentials APIs, create a workload identity pool and an OIDC provider for issuer `https://gitlab.com/` (restrict it with an attribute condition to this project's path), create a service account with the Cloud Run Admin, Service Account User, Cloud Build Editor and Storage Admin roles, and let the pool's principal for this project impersonate it. Then set the three variables, run the `deploy-cloud-run` job once from the default branch, and open the URL it prints. Do not run it again after the submission deadline.
