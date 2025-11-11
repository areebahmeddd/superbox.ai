import os
import re
import time
import shutil
import tempfile
import subprocess
from datetime import datetime

import requests

from mcpbox.shared.config import Config, load_env


def extract_repository(repo_url):
    repo_url = repo_url.strip().rstrip("/")
    if repo_url.startswith("git@github.com:"):
        repo_url = repo_url.replace("git@github.com:", "")
    elif "github.com/" in repo_url:
        repo_url = repo_url.split("github.com/")[-1]

    repo_url = repo_url.replace(".git", "")
    parts = repo_url.split("/")
    if len(parts) >= 2:
        return parts[-2], parts[-1]
    return None, None


def generate_key(owner, repo, organization):
    safe_owner = re.sub(r"[^a-zA-Z0-9_\-.]", "_", owner)
    safe_repo = re.sub(r"[^a-zA-Z0-9_\-.]", "_", repo)
    return f"{organization}_{safe_owner}_{safe_repo}"


def create_project(project_key, project_name, sonar_host, sonar_token, sonar_org):
    url = f"{sonar_host}/api/projects/create"
    params = {"organization": sonar_org, "project": project_key, "name": project_name}
    headers = {"Authorization": f"Bearer {sonar_token}"}

    try:
        response = requests.post(url, params=params, headers=headers, timeout=30)
        if response.status_code == 200:
            return True

        if response.status_code == 400:
            error_msg = response.text.lower()
            if "already exists" in error_msg or "already" in error_msg:
                return True

            return False

        return False
    except requests.exceptions.RequestException:
        return False


def clone_repository(repo_url, target_dir):
    result = subprocess.run(
        ["git", "clone", "--depth", "1", repo_url, target_dir], capture_output=True, text=True
    )
    if result.returncode != 0:
        return False

    return True


def run_scanner(repo_path, project_key, sonar_host, sonar_token, sonar_org):
    original_dir = os.getcwd()
    os.chdir(repo_path)
    try:
        result = subprocess.run(
            [
                "sonar-scanner",
                f"-Dsonar.projectKey={project_key}",
                f"-Dsonar.organization={sonar_org}",
                "-Dsonar.sources=.",
                "-Dsonar.sourceEncoding=UTF-8",
                f"-Dsonar.host.url={sonar_host}",
                f"-Dsonar.login={sonar_token}",
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            return False

        return True
    except subprocess.TimeoutExpired:
        return False
    finally:
        os.chdir(original_dir)


def wait_analysis(project_key, sonar_host, sonar_token, max_wait=60):
    url = f"{sonar_host}/api/ce/component"
    params = {"component": project_key}
    headers = {"Authorization": f"Bearer {sonar_token}"}
    start_time = time.time()
    while time.time() - start_time < max_wait:
        try:
            response = requests.get(url, params=params, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get("queue"):
                    time.sleep(3)
                    continue

                current = data.get("current")
                if current:
                    status = current.get("status")
                    if status == "SUCCESS":
                        return True
                    elif status in ["PENDING", "IN_PROGRESS"]:
                        time.sleep(3)
                        continue
                    else:
                        return False
                else:
                    return True

            time.sleep(3)
        except Exception:
            time.sleep(3)

    return True


def fetch_issues(project_key, sonar_host, sonar_token):
    url = f"{sonar_host}/api/issues/search"
    headers = {"Authorization": f"Bearer {sonar_token}"}
    all_issues = []
    page = 1
    page_size = 500
    while True:
        params = {"componentKeys": project_key, "ps": page_size, "p": page}
        try:
            response = requests.get(url, params=params, headers=headers, timeout=30)
            if response.status_code != 200:
                break

            data = response.json()
            issues = data.get("issues", [])
            all_issues.extend(issues)
            total = data.get("total", 0)
            if len(all_issues) >= total or len(issues) < page_size:
                break

            page += 1
        except Exception:
            break

    return all_issues


def fetch_hotspots(project_key, sonar_host, sonar_token):
    url = f"{sonar_host}/api/hotspots/search"
    headers = {"Authorization": f"Bearer {sonar_token}"}
    all_hotspots = []
    page = 1
    page_size = 500
    while True:
        params = {"projectKey": project_key, "ps": page_size, "p": page}
        try:
            response = requests.get(url, params=params, headers=headers, timeout=30)
            if response.status_code != 200:
                break

            data = response.json()
            hotspots = data.get("hotspots", [])
            all_hotspots.extend(hotspots)
            paging = data.get("paging", {})
            total = paging.get("total", 0)
            if len(all_hotspots) >= total or len(hotspots) < page_size:
                break

            page += 1
        except Exception:
            break

    return all_hotspots


def fetch_measures(project_key, sonar_host, sonar_token):
    url = f"{sonar_host}/api/measures/component"
    headers = {"Authorization": f"Bearer {sonar_token}"}
    metric_keys = [
        "ncloc",
        "coverage",
        "bugs",
        "vulnerabilities",
        "code_smells",
        "security_hotspots",
        "sqale_rating",
        "reliability_rating",
        "security_rating",
        "duplicated_lines_density",
        "complexity",
    ]
    params = {"component": project_key, "metricKeys": ",".join(metric_keys)}
    try:
        response = requests.get(url, params=params, headers=headers, timeout=30)
        if response.status_code != 200:
            return {}

        data = response.json()
        component = data.get("component", {})
        measures = component.get("measures", [])
        metrics = {}
        for measure in measures:
            metric = measure.get("metric")
            value = measure.get("value")
            metrics[metric] = value

        return metrics
    except Exception:
        return {}


def create_report(repo_name, project_key, issues, hotspots, metrics, sonar_host):
    """Create report data structure (no file generation, data goes to S3)"""
    bugs = [i for i in issues if i.get("type") == "BUG"]
    vulnerabilities = [i for i in issues if i.get("type") == "VULNERABILITY"]
    code_smells = [i for i in issues if i.get("type") == "CODE_SMELL"]

    report = {
        "metadata": {
            "repository": repo_name,
            "project_key": project_key,
            "analysis_date": datetime.now().isoformat(),
            "sonarcloud_url": f"{sonar_host}/dashboard?id={project_key}",
        },
        "issue_counts": {
            "total": len(issues),
            "bugs": len(bugs),
            "vulnerabilities": len(vulnerabilities),
            "code_smells": len(code_smells),
            "security_hotspots": len(hotspots),
        },
        "metrics": metrics,
        "quality_gate": {"status": metrics.get("alert_status", "N/A")},
        "quality_ratings": {
            "reliability": metrics.get("reliability_rating", "N/A"),
            "security": metrics.get("security_rating", "N/A"),
            "maintainability": metrics.get("sqale_rating", "N/A"),
        },
    }

    return report


def run_analysis(repo_url, env_path=None):
    load_env(env_path)

    SONAR_HOST = "https://sonarcloud.io"
    cfg = Config()

    SONAR_TOKEN = cfg.SONAR_TOKEN
    SONAR_ORGANIZATION = cfg.SONAR_ORGANIZATION

    print("[Sonar] Starting analysis")
    owner, repo = extract_repository(repo_url)
    if not owner or not repo:
        raise ValueError("Error: Could not parse repository URL")

    repo_name = f"{owner}_{repo}"
    project_key = generate_key(owner, repo, SONAR_ORGANIZATION)
    print(f"[Sonar] Project {owner}/{repo} (key={project_key})")

    tmp_dir = tempfile.mkdtemp(prefix="sonarcloud_auto_")
    repo_path = os.path.join(tmp_dir, "repo")

    try:
        if not create_project(
            project_key, f"{owner}/{repo}", SONAR_HOST, SONAR_TOKEN, SONAR_ORGANIZATION
        ):
            pass

        print("[Sonar] Cloning repository")
        if not clone_repository(repo_url, repo_path):
            raise RuntimeError("Failed to clone repository")

        print("[Sonar] Running scanner")
        if not run_scanner(repo_path, project_key, SONAR_HOST, SONAR_TOKEN, SONAR_ORGANIZATION):
            raise RuntimeError("Failed to run scanner")
        print("[Sonar] Analysis submitted")

        print("[Sonar] Waiting for analysis results")
        wait_analysis(project_key, SONAR_HOST, SONAR_TOKEN)
        print("[Sonar] Fetching issues, hotspots, and metrics")
        issues = fetch_issues(project_key, SONAR_HOST, SONAR_TOKEN)
        hotspots = fetch_hotspots(project_key, SONAR_HOST, SONAR_TOKEN)
        metrics = fetch_measures(project_key, SONAR_HOST, SONAR_TOKEN)

        report_data = create_report(repo_name, project_key, issues, hotspots, metrics, SONAR_HOST)
        total_issues = len(issues)
        total_hotspots = len(hotspots)
        coverage = metrics.get("coverage", "N/A")
        print(
            f"[Sonar] Results: issues={total_issues}, hotspots={total_hotspots}, coverage={coverage}"
        )

        return {
            "success": True,
            "report_data": report_data,
            "project_key": project_key,
            "repo_url": repo_url,
            "owner": owner,
            "repo": repo,
        }

    finally:
        os.chdir("/")
        shutil.rmtree(tmp_dir, ignore_errors=True)
        print("[Sonar] Cleanup complete")
