"""What each run of the app workflow (.github/workflows/desktop-probe.yml) does. Standard library only.

    python packaging/ci_scope.py                      # GitHub outputs for this run (see main)
    python packaging/ci_scope.py --check-release-tag  # a tag must match the source version and sit on main

Owner, 2026-10-06: Actions minutes are limited and Windows minutes count double. So nothing is built or
tested twice, and anything uncertain (no earlier run found, history rewritten, the API unreachable) builds
and tests:

- Linux suite. A push to main runs it in full, unless only documents changed since the last commit whose
  full suite passed: then it runs the tests that read them. Measured from that commit, not the previous push,
  so a code push whose run was cancelled still gets the full suite. A manual run skips it when an earlier
  run passed it on this exact commit. Daily and tag runs always run it.
- Windows app. A tag and a manual run build it. The daily run builds it when a file that can reach it
  changed since the last commit whose Windows build succeeded (so a failed or cancelled build is redone).
  A manual run on main reuses an earlier run's unexpired ZIP of this exact commit.
- Phone app. A manual run on main makes matched test builds; a release tag builds the same signed APK
  for the permanent Windows and Android beta release (docs/ARCHITECTURE.md › Build and release).
  The daily run builds and checks it (no key, nothing offered) when a file that reaches it changed since
  its last successful build.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Files that never reach the Windows app or its build. Anything else (code, tests, packaging, locks, this
# workflow, Markdown inside lightning/ or packaging/) does.
_NEVER_SHIPPED = (
    re.compile(r"^docs/"),
    re.compile(r"^user feedback/"),
    re.compile(r"^Claude outputs/"),
    re.compile(r"^tools/"),  # helpers for the people and AIs working here; nothing imports them
    re.compile(r"^(?!lightning/|packaging/)[^\n]*\.md$"),
    re.compile(r"^Lightning\.desktop$"),
    re.compile(r"^run\.sh$"),
    re.compile(r"^android/"),  # the phone app's own build
    re.compile(r"^requirements/android\."),
    re.compile(r"^\.github/workflows/android-"),
    re.compile(r"^packaging/(phone_build\.py|android-)"),
)
# Files that reach the phone app or its build.
_REACHES_PHONE = (
    re.compile(r"^lightning/"),
    re.compile(r"^android/"),
    re.compile(r"^requirements/android\."),
    re.compile(r"^packaging/(phone_build\.py|android-)"),
    re.compile(r"^\.github/workflows/(android-app|desktop-probe)\.yml$"),
    re.compile(r"^tests/fixtures/roundtrip/"),
)
# Documents: a push that changes nothing else since the last full suite runs only the tests that read them.
_DOCS_ONLY = (
    re.compile(r"^docs/"),
    re.compile(r"^user feedback/"),
    re.compile(r"^Claude outputs/"),
    re.compile(r"^[^/]+\.md$"),  # NOW, OWNER, CHANGELOG, AGENTS, README and the like
)
ALWAYS_DOCS_TESTS = ("tests/test_docs_structure.py", "tests/test_changelog.py")

WINDOWS_JOBS = {"Build and test the Windows app"}
PHONE_JOBS = {"Phone app / Build and check the phone app"}  # the phone build as this workflow calls it
SUITE_JOB = "Full test suite (Linux)"
SUITE_STEP = "Full test suite"  # the step that runs it: the job also succeeds when the suite was skipped
WINDOWS_ARTIFACT = re.compile(r"Lightning-v\S+-dev-\S+-Windows-x64")  # a development build's ZIP artifact


def cannot_reach_app(path: str) -> bool:
    return any(pattern.search(path) for pattern in _NEVER_SHIPPED)


def reaches_phone(path: str) -> bool:
    return any(pattern.search(path) for pattern in _REACHES_PHONE)


def docs_only(path: str) -> bool:
    return any(pattern.search(path) for pattern in _DOCS_ONLY)


def suite_passed(job: dict) -> bool:
    """Whether this job ran the full Linux suite and it passed (not merely skipped it)."""
    return job.get("name") == SUITE_JOB and any(
        step.get("name") == SUITE_STEP and step.get("conclusion") == "success" for step in job.get("steps", []))


# ---------------------------------------------------------------- earlier runs (GitHub API)
def github_api(path: str) -> dict:
    request = urllib.request.Request(
        f"{os.environ.get('GITHUB_API_URL', 'https://api.github.com')}{path}",
        headers={"Authorization": f"Bearer {os.environ['GH_TOKEN']}", "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def _workflow() -> tuple[str, str]:
    """This repository and this workflow's file name, or empty strings outside GitHub Actions."""
    if not os.environ.get("GH_TOKEN"):
        return "", ""
    return (os.environ.get("GITHUB_REPOSITORY", ""),
            os.environ.get("GITHUB_WORKFLOW_REF", "").split("@")[0].rsplit("/", 1)[-1])


def _newest_on_main(api, events: tuple[str, ...], matches) -> str | None:
    """The commit of the newest completed run on main, among these events (all if none), whose jobs match."""
    repo, workflow = _workflow()
    if not repo or not workflow:
        return None
    query = f"/repos/{repo}/actions/workflows/{workflow}/runs?branch=main&status=completed"
    runs = []
    for event in events or ("",):
        runs += api(query + (f"&event={event}" if event else "") + "&per_page=30").get("workflow_runs", [])
    runs.sort(key=lambda run: run.get("created_at", ""), reverse=True)
    for run in runs:
        if matches(api(f"/repos/{repo}/actions/runs/{run['id']}/jobs?per_page=100").get("jobs", [])):
            return run["head_sha"]
    return None


def last_windows_build(api=github_api, jobs_wanted: set[str] = WINDOWS_JOBS) -> str | None:
    """The commit of the newest run on main whose Windows job (or, with PHONE_JOBS, phone job) succeeded,
    or None if unknown. Only daily and manual runs build either on main, so only they are read: a day of
    pushes would fill a page of all runs."""
    try:
        return _newest_on_main(api, ("schedule", "workflow_dispatch"), lambda jobs: any(
            job.get("name") in jobs_wanted and job.get("conclusion") == "success" for job in jobs))
    except Exception as exc:  # no answer means no baseline, and no baseline means build
        print(f"Could not read earlier runs ({type(exc).__name__}); building to be safe.")
        return None


def last_full_suite(api=github_api) -> str | None:
    """The commit of the newest run on main that ran the full Linux suite and passed it, or None."""
    try:
        return _newest_on_main(api, (), lambda jobs: any(suite_passed(job) for job in jobs))
    except Exception as exc:  # no answer means the full suite
        print(f"Could not read earlier runs ({type(exc).__name__}); running the full suite.")
        return None


def earlier_runs(sha: str, api=github_api) -> dict[str, str]:
    """What earlier runs of this workflow already did for this exact commit: the newest run whose Windows
    build succeeded and whose ZIP artifact has not expired (reuse_run, reuse_artifact), and whether the
    full Linux suite passed on it (suite=skip). An unknown answer means build and test."""
    nothing = {"reuse_run": "", "reuse_artifact": "", "suite": "run"}
    repo, workflow = _workflow()
    if not repo or not workflow or not re.fullmatch(r"[0-9a-f]{40}", sha):
        return nothing
    found = dict(nothing)
    current = os.environ.get("GITHUB_RUN_ID", "")
    try:
        runs = api(f"/repos/{repo}/actions/workflows/{workflow}/runs?head_sha={sha}&status=completed&per_page=30")
        for run in runs.get("workflow_runs", []):
            if run.get("head_sha") != sha or str(run.get("id")) == current:
                continue
            jobs = api(f"/repos/{repo}/actions/runs/{run['id']}/jobs?per_page=100").get("jobs", [])
            if any(suite_passed(job) for job in jobs):
                found["suite"] = "skip"
            built = any(job.get("name") in WINDOWS_JOBS and job.get("conclusion") == "success" for job in jobs)
            if built and not found["reuse_run"]:
                artifacts = api(f"/repos/{repo}/actions/runs/{run['id']}/artifacts?per_page=100").get("artifacts", [])
                usable = [a["name"] for a in artifacts
                          if WINDOWS_ARTIFACT.fullmatch(a.get("name", "")) and not a.get("expired", True)]
                if usable:
                    found.update(reuse_run=str(run["id"]), reuse_artifact=usable[0], suite="skip")
    except Exception as exc:  # no answer means build and test
        print(f"Could not read earlier runs of this commit ({type(exc).__name__}); building and testing.")
        return nothing
    return found


# ---------------------------------------------------------------- what changed, and the decisions
def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)


def changed_since(baseline: str | None, sha: str, what: str) -> tuple[list[str] | None, str]:
    """The files changed from the last successful build to this commit, or None and why that is unknown."""
    if not baseline:
        return None, f"no earlier successful {what} build to compare with"
    if _git("cat-file", "-e", f"{baseline}^{{commit}}").returncode != 0:
        return None, f"last built commit {baseline[:8]} is not in this history"
    if _git("merge-base", "--is-ancestor", baseline, sha).returncode != 0:
        return None, f"last built commit {baseline[:8]} is not an ancestor of this push"
    # --no-renames: a file moved out of the app (say into docs/) lists its old path too, so it builds.
    diff = _git("diff", "--no-renames", "--name-only", baseline, sha)
    if diff.returncode != 0:
        return None, "could not list changed files"
    return [line for line in diff.stdout.splitlines() if line.strip()], ""


def build_windows(event: str, ref: str, baseline: str | None, sha: str) -> tuple[bool, str]:
    if ref.startswith("refs/tags/"):
        return True, "release tag"
    if event == "push":
        return False, "a push runs the Linux suite only; Windows builds daily, on a tag or when run by hand"
    if event != "schedule":
        return True, f"{event or 'manual'} run"
    changed, why = changed_since(baseline, sha, "Windows")
    if changed is None:
        return True, why
    if not changed:
        return False, f"nothing changed since the last build ({baseline[:8]})"
    reaching = [path for path in changed if not cannot_reach_app(path)]
    if reaching:
        return True, f"{len(reaching)} changed file(s) can reach the app, e.g. {reaching[0]}"
    return False, f"only documentation changed since {baseline[:8]}, the last commit built ({len(changed)} file(s))"


def build_phone_daily(event: str, ref: str, baseline: str | None, sha: str) -> tuple[bool, str]:
    """Whether the daily run builds and checks the phone app (no key needed, nothing offered): only when a
    file that reaches the phone changed since its last successful build. Anything uncertain builds."""
    if event != "schedule" or ref != "refs/heads/main":
        return False, "only the daily run builds the phone on its own"
    changed, why = changed_since(baseline, sha, "phone")
    if changed is None:
        return True, why
    reaching = [path for path in changed if reaches_phone(path)]
    if reaching:
        return True, f"{len(reaching)} changed file(s) reach the phone, e.g. {reaching[0]}"
    return False, f"nothing that reaches the phone changed since {baseline[:8]}"


def docs_tests(changed: list[str], tests_dir: Path | None = None) -> list[str]:
    """The tests for a documents-only change: the documentation tests, and every test file that names a
    changed document (a test that reads a document names it)."""
    tests_dir = tests_dir or ROOT / "tests"
    names = {Path(path).name for path in changed}
    chosen = set(ALWAYS_DOCS_TESTS)
    for test in sorted(tests_dir.glob("test_*.py")):
        if any(name in test.read_text(encoding="utf-8") for name in names):
            chosen.add(f"tests/{test.name}")
    return sorted(chosen)


def push_suite(baseline: str | None, sha: str) -> tuple[str, list[str], str]:
    """For a push to main: "docs" and the tests to run when only documents changed since the last commit
    whose full suite passed (so a cancelled run's code is never let through), else "run"."""
    changed, why = changed_since(baseline, sha, "full-suite")
    if changed is None:
        return "run", [], why
    if changed and all(docs_only(path) for path in changed):
        return "docs", docs_tests(changed), f"only documents changed since {baseline[:8]}, the last full suite"
    return "run", [], "code changed since the last full suite" if changed else "nothing changed; run anyway"


# ---------------------------------------------------------------- releases
def source_version() -> str:
    text = (ROOT / "lightning" / "__init__.py").read_text(encoding="utf-8")
    found = re.search(r'^DISPLAY_VERSION = "([^"]+)"$', text, re.M)
    if not found:
        raise SystemExit("::error::lightning/__init__.py has no DISPLAY_VERSION")
    return found.group(1)


def check_release_tag(tag: str, sha: str) -> list[str]:
    """Problems that stop a release; empty when the tag may be released."""
    problems = []
    version = source_version()
    if tag != f"v{version}":
        problems.append(f"Tag {tag} does not match the source version v{version} (lightning/__init__.py). "
                        "Bump the version in lightning/__init__.py and pyproject.toml, push, then tag that commit.")
    if _git("fetch", "--no-tags", "origin", "main").returncode != 0:
        problems.append("Could not fetch origin/main to check where the tag points.")
    elif _git("merge-base", "--is-ancestor", sha, "origin/main").returncode != 0:
        problems.append(f"Tag {tag} points at {sha[:8]}, which is not on main. Release only commits on main.")
    return problems


# ---------------------------------------------------------------- what the run's page says
def manual_run_notes(ref: str, sha: str, values: dict[str, str], reason: str, has_key: bool | None,
                     has_fingerprint: bool) -> list[tuple[str, str]]:
    """What a manual run will make, as (level, text) lines for the run's page, said in its first minute."""
    if values["phone"] != "true":
        return [("warning", f"A manual run on {ref.removeprefix('refs/heads/')} builds the Windows app only; "
                            "the matched PC and phone test builds run only on main.")]
    windows = reason if values["reuse_run"] else "built and tested in this run"
    notes = [("notice", f"Matched test builds of {sha[:8]}. Windows: {windows}. Linux suite: "
                        + ("already passed on this commit, not run again." if values["suite"] == "skip" else "runs now."))]
    if has_key is None:
        notes.append(("notice", "Android signing key availability is checked only in the protected android-signing job."))
    elif not has_key:
        notes.append(("warning", "No Android signing key yet: both apps are built and checked, "
                                 "the Windows ZIP is uploaded, but the phone build stops at signing and no matched "
                                 "pair is offered."))
    elif not has_fingerprint:
        notes.append(("warning", "The Android signing key is set but its public fingerprint is not committed as "
                                 "packaging/android-test-certificate.sha256: the phone build will stop after signing."))
    return notes


def tell(notes: list[tuple[str, str]]) -> None:
    """Annotations on the run's page, and the same lines in its summary."""
    for level, text in notes:
        print(f"::{level}::{text}")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary and notes:
        with open(summary, "a", encoding="utf-8") as stream:
            stream.write("".join(f"- {text}\n" for _, text in notes))


def main(argv: list[str]) -> int:
    """Writes build_windows, suite (run, docs or skip), docs_tests, phone, phone_daily, reuse_run and
    reuse_artifact to the step's GitHub outputs."""
    sha = os.environ.get("GITHUB_SHA", "HEAD")
    if "--check-release-tag" in argv:
        tag = os.environ.get("GITHUB_REF_NAME", "")
        problems = check_release_tag(tag, sha)
        for problem in problems:
            print(f"::error::{problem}")
        if not problems:
            print(f"Release tag {tag} matches the source version and is on main.")
        return 1 if problems else 0
    event, ref = os.environ.get("GITHUB_EVENT_NAME", ""), os.environ.get("GITHUB_REF", "")
    on_main = ref == "refs/heads/main"
    values = {"reuse_run": "", "reuse_artifact": "", "suite": "run", "docs_tests": "", "phone": "false",
              "phone_daily": "false"}
    # Only the daily run compares with the last Windows build (a push never builds Windows).
    build, reason = build_windows(event, ref, last_windows_build() if event == "schedule" and on_main else None, sha)
    if event == "push" and on_main:
        suite, tests, why = push_suite(last_full_suite(), sha)
        values.update(suite=suite, docs_tests=" ".join(tests))
        print(f"Linux suite: {suite} ({why})" + (f": {' '.join(tests)}" if tests else ""))
    if event == "schedule" and on_main:
        daily, why = build_phone_daily(event, ref, last_windows_build(jobs_wanted=PHONE_JOBS), sha)
        values["phone_daily"] = "true" if daily else "false"
        print(f"Build the phone app: {'yes' if daily else 'no'} ({why})")
    if event == "workflow_dispatch" and on_main:
        values.update(earlier_runs(sha), phone="true")
        if values["reuse_run"]:
            build, reason = False, f"run {values['reuse_run']} built and tested this commit; its ZIP is reused"
    if ref.startswith("refs/tags/v"):
        values["phone"] = "true"
    print(f"Build the Windows app: {'yes' if build else 'no'} ({reason})")
    if event == "workflow_dispatch":
        tell(manual_run_notes(ref, sha, values, reason, None,
                              (ROOT / "packaging" / "android-test-certificate.sha256").exists()))
    values["build_windows"] = "true" if build else "false"
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as stream:
            stream.write("".join(f"{key}={value}\n" for key, value in values.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
