from __future__ import annotations

import pytest

from conftest import make_job
from jobradar.skills import KNOWN_SKILLS, SkillProfile


def mentioned(text: str) -> set[str]:
    return {name for name, pattern in KNOWN_SKILLS.items() if pattern.search(text)}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Experience with Python, Go or Rust.", {"Python", "Go", "Rust"}),
        ("Strong Golang skills.", {"Go"}),
        ("Go beyond what you thought possible.", set()),
        ("Work with our Go-to-market team.", set()),
        ("Logs go to Elasticsearch and Kibana.", {"ELK"}),
        ("We deploy Helm charts to EKS.", {"Helm", "Kubernetes"}),
        ("You will be at the helm of our platform.", set()),
        ("Backend services in C# and ASP.NET Core.", {"C#", ".NET"}),
        ("Read more at example.net today.", set()),
        ("k8s, Terraform and Amazon Web Services.", {"Kubernetes", "Terraform", "AWS"}),
        ("Pipelines in Azure DevOps.", {"Azure", "Azure DevOps"}),
        ("Linux servers (Ubuntu, RHEL).", {"Linux"}),
        ("Postgres and MariaDB.", {"PostgreSQL", "MySQL"}),
    ],
)
def test_known_skills(text, expected):
    assert mentioned(text) == expected


def test_fit_compares_your_tools_with_every_tool_the_ad_names():
    profile = SkillProfile.from_names(["aws", "Terraform", "Kubernetes"])
    job = make_job(description="Terraform on AWS. Terraform modules. You know GCP, Go and Python.")
    profile.apply(job)
    assert job.skills == ["Terraform", "AWS"]
    assert job.gaps == ["GCP", "Go", "Python"]
    assert job.fit == 40


def test_names_outside_the_list_match_as_whole_words():
    profile = SkillProfile.from_names(["Crossplane"])
    job = make_job(description="We use Crossplane.")
    profile.apply(job)
    assert (job.fit, job.skills) == (100, ["Crossplane"])
    other = make_job(description="Crossplanes everywhere.")
    profile.apply(other)
    assert other.fit is None


def test_a_companys_own_product_is_ignored():
    profile = SkillProfile.from_names(["Datadog", "AWS"])
    job = make_job(company="Datadog", description="Datadog runs on AWS. Datadog is great.")
    profile.apply(job)
    assert (job.fit, job.skills, job.gaps) == (100, ["AWS"], [])


@pytest.mark.parametrize(
    ("profile", "description"),
    [
        (SkillProfile(), "Terraform on AWS."),
        (SkillProfile.from_names(["AWS"]), ""),
        (SkillProfile.from_names(["AWS"]), "A friendly team in Berlin."),
    ],
)
def test_no_fit_without_a_profile_ad_text_or_tools(profile, description):
    job = make_job(description=description)
    profile.apply(job)
    assert job.fit is None
    assert job.skills == job.gaps == []


def test_empty_skill_names_are_rejected():
    with pytest.raises(ValueError, match="cannot be empty"):
        SkillProfile.from_names(["AWS", " "])
