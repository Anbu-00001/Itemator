"""The per-merge-request preview of the reviewer's map (.gitlab-ci.yml, job map-preview): a Pages parallel deployment."""
import pathlib

import yaml

CI = yaml.safe_load((pathlib.Path(__file__).resolve().parent.parent / ".gitlab-ci.yml").read_text())
JOB = CI["map-preview"]


def test_the_preview_runs_only_in_merge_request_pipelines():
    assert JOB["rules"] == [{"if": '$CI_PIPELINE_SOURCE == "merge_request_event"'}]


def test_the_preview_is_a_parallel_deployment_per_request_that_expires():
    assert JOB["pages"] == {"path_prefix": "mr-$CI_MERGE_REQUEST_IID", "expire_in": "7 days"}
    assert JOB["environment"] == {"name": "Pages MR $CI_MERGE_REQUEST_IID", "url": "$CI_PAGES_URL"}
    assert JOB["artifacts"]["paths"] == ["public"] and JOB["stage"] == "deploy"


def test_the_preview_maps_the_requests_own_commits():
    script = " ".join(JOB["script"])
    assert '--base "$CI_MERGE_REQUEST_DIFF_BASE_SHA"' in script and '--head "$CI_COMMIT_SHA"' in script and "--commits" in script
    assert "--out public" in script and JOB["variables"]["GIT_DEPTH"] == "0"


def test_the_production_page_job_is_not_touched():
    assert CI["shipped-page"]["pages"] is True and CI["shipped-page"]["rules"] == [{"if": "$CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH"}]


def test_every_script_line_is_a_plain_string():
    """A ": " inside an unquoted script line turns it into a mapping; YAML still parses, but GitLab rejects the pipeline."""
    for name, job in CI.items():
        if isinstance(job, dict):
            for key in ("before_script", "script", "after_script"):
                for line in job.get(key) or []:
                    assert isinstance(line, str), (name, key, line)
