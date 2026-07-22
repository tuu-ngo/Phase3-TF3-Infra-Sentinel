from pathlib import Path


TERRAFORM = Path("infra/live/production/kyverno-ecr.tf").read_text()


def test_kyverno_role_is_bound_only_to_expected_service_accounts():
    assert 'name               = "${var.cluster_name}-kyverno-ecr"' in TERRAFORM
    assert 'actions = ["sts:AssumeRoleWithWebIdentity"]' in TERRAFORM
    for service_account in (
        "kyverno-admission-controller",
        "kyverno-background-controller",
    ):
        assert f"system:serviceaccount:kyverno:{service_account}" in TERRAFORM
    assert "kyverno-cleanup-controller" not in TERRAFORM
    assert "kyverno-reports-controller" not in TERRAFORM
    assert "system:serviceaccount:kube-system" not in TERRAFORM


def test_kyverno_role_has_read_only_first_party_ecr_actions():
    for action in (
        "ecr:GetAuthorizationToken",
        "ecr:BatchCheckLayerAvailability",
        "ecr:BatchGetImage",
        "ecr:DescribeImages",
        "ecr:DescribeRepositories",
        "ecr:GetDownloadUrlForLayer",
    ):
        assert f'"{action}"' in TERRAFORM
    assert '"ecr:PutImage"' not in TERRAFORM
    assert '"ecr:DeleteRepository"' not in TERRAFORM
    assert ":repository/techx-corp" in TERRAFORM
