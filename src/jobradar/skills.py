from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from .models import Job


def _skill(pattern: str, *, ignore_case: bool = True) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE if ignore_case else 0)


KNOWN_SKILLS: dict[str, re.Pattern[str]] = {
    # Cloud
    "AWS": _skill(r"\baws\b|\bamazon\s+web\s+services\b"),
    "Azure": _skill(r"\bazure\b"),
    "GCP": _skill(r"\bgcp\b|\bgoogle\s+cloud\b"),
    "Serverless": _skill(r"\bserverless\b|\baws\s+lambda\b|\b(?:azure|cloud)\s+functions\b"),
    "OpenStack": _skill(r"\bopenstack\b"),
    "VMware": _skill(r"\bvmware\b|\bvsphere\b"),
    # Infrastructure as code
    "Terraform": _skill(r"\bterraform\b|\bopentofu\b"),
    "Pulumi": _skill(r"\bpulumi\b"),
    "CloudFormation": _skill(r"\bcloudformation\b"),
    "Bicep": _skill(r"\bbicep\b"),
    "Ansible": _skill(r"\bansible\b"),
    "Puppet": _skill(r"\bpuppet\b"),
    "Chef": _skill(r"\bchef\b"),
    "Packer": _skill(r"\bpacker\b"),
    # Containers
    "Docker": _skill(r"\bdocker\b|\bpodman\b"),
    "Kubernetes": _skill(r"\bkubernetes\b|\bk8s\b|\beks\b|\baks\b|\bgke\b"),
    "Helm": _skill(r"(?<!the )\bhelm\b"),
    "OpenShift": _skill(r"\bopenshift\b"),
    "Service mesh": _skill(r"\bistio\b|\blinkerd\b|\bservice\s+mesh\b"),
    # CI/CD
    "GitHub Actions": _skill(r"\bgithub\s+actions\b"),
    "GitLab CI": _skill(r"\bgitlab\b"),
    "Jenkins": _skill(r"\bjenkins\b"),
    "Azure DevOps": _skill(r"\bazure\s+(?:devops|pipelines)\b"),
    "ArgoCD": _skill(r"\bargo(?:\s?cd)?\b"),
    "Flux": _skill(r"\bflux\s?cd\b"),
    "CircleCI": _skill(r"\bcircle\s?ci\b"),
    "TeamCity": _skill(r"\bteamcity\b"),
    # Observability
    "Prometheus": _skill(r"\bprometheus\b"),
    "Grafana": _skill(r"\bgrafana\b"),
    "Datadog": _skill(r"\bdatadog\b"),
    "ELK": _skill(r"\belk\b|\belastic\s?search\b|\bkibana\b|\blogstash\b|\bopensearch\b"),
    "Splunk": _skill(r"\bsplunk\b"),
    "New Relic": _skill(r"\bnew\s?relic\b"),
    "OpenTelemetry": _skill(r"\bopen\s?telemetry\b|\botel\b"),
    # Security
    "Vault": _skill(r"\bvault\b"),
    "Trivy": _skill(r"\btrivy\b"),
    "Checkov": _skill(r"\bcheckov\b"),
    "Semgrep": _skill(r"\bsemgrep\b"),
    "SonarQube": _skill(r"\bsonar(?:qube|cloud)?\b"),
    "Snyk": _skill(r"\bsnyk\b"),
    # Languages
    "Python": _skill(r"\bpython\b"),
    "Go": _skill(r"\b[Gg]olang\b|(?:(?<=[a-z,] )|(?<=[(/]))Go\b(?!-)", ignore_case=False),
    "Bash": _skill(r"\bbash\b|\bshell\s+script"),
    "PowerShell": _skill(r"\bpowershell\b"),
    "C#": _skill(r"(?<!\w)c#(?!\w)"),
    ".NET": _skill(r"(?<![\w.])\.net\b|\basp\.net\b|\bdotnet\b"),
    "Java": _skill(r"\bjava\b"),
    "JavaScript": _skill(r"\bjavascript\b|\bnode\.?js\b"),
    "TypeScript": _skill(r"\btypescript\b"),
    "Ruby": _skill(r"\bruby\b"),
    "Rust": _skill(r"\brust\b"),
    # Data
    "PostgreSQL": _skill(r"\bpostgres(?:ql)?\b"),
    "MySQL": _skill(r"\bmysql\b|\bmariadb\b"),
    "SQL Server": _skill(r"\bsql\s+server\b|\bmssql\b"),
    "MongoDB": _skill(r"\bmongo(?:db)?\b"),
    "Redis": _skill(r"\bredis\b"),
    "Kafka": _skill(r"\bkafka\b"),
    "RabbitMQ": _skill(r"\brabbitmq\b"),
    # Systems
    "Linux": _skill(r"\blinux\b|\bubuntu\b|\brhel\b|\bdebian\b|\bcentos\b"),
    "Windows Server": _skill(r"\bwindows\s+server\b"),
    "Nginx": _skill(r"\bnginx\b"),
}


@dataclass(frozen=True)
class SkillProfile:
    """The owner's skills, compared with the tools each ad names."""

    have: frozenset[str] = frozenset()
    patterns: tuple[tuple[str, re.Pattern[str]], ...] = ()

    @classmethod
    def from_names(cls, names: Iterable[str]) -> SkillProfile:
        known = {name.lower(): name for name in KNOWN_SKILLS}
        patterns = dict(KNOWN_SKILLS)
        have: set[str] = set()
        for raw in names:
            cleaned = " ".join(str(raw).split())
            if not cleaned:
                raise ValueError("Skill names cannot be empty")
            name = known.get(cleaned.lower(), cleaned)
            # Anything outside the list is matched as a whole word or phrase.
            patterns.setdefault(name, re.compile(rf"(?<!\w){re.escape(name)}(?!\w)", re.I))
            have.add(name)
        return cls(have=frozenset(have), patterns=tuple(patterns.items()) if have else ())

    def apply(self, job: Job) -> None:
        """Set job.fit (0-100), job.skills (yours, most mentioned first) and job.gaps."""
        if not self.have or not job.description:
            return
        counts = {
            name: len(pattern.findall(job.description))
            for name, pattern in self.patterns
            if not pattern.search(job.company)
        }
        mentioned = sorted(
            (name for name, count in counts.items() if count), key=lambda n: (-counts[n], n)
        )
        if not mentioned:
            return
        job.skills = [name for name in mentioned if name in self.have]
        job.gaps = [name for name in mentioned if name not in self.have]
        job.fit = round(100 * len(job.skills) / len(mentioned))
