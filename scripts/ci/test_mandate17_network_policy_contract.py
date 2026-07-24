from pathlib import Path

import yaml


REPO = Path(__file__).resolve().parents[2]
INFRA = REPO / "gitops/infrastructure"
STAGED = INFRA / "network-policy-staged"

EXPECTED_FILES = {
    "00-otel-gateway.yaml",
    "01-grafana.yaml",
    "02-jaeger.yaml",
    "03-prometheus.yaml",
    "04-opensearch.yaml",
    "05-load-generator.yaml",
    "06-cloudflared.yaml",
    "07-aiops-engine.yaml",
    "10-quote.yaml",
    "11-currency.yaml",
    "12-payment.yaml",
    "13-email.yaml",
    "14-ad.yaml",
    "15-image-provider.yaml",
    "16-llm.yaml",
    "20-product-catalog.yaml",
    "21-cart.yaml",
    "22-accounting.yaml",
    "23-fraud-detection.yaml",
    "30-shipping.yaml",
    "31-recommendation.yaml",
    "32-product-reviews.yaml",
    "33-checkout.yaml",
    "34-frontend.yaml",
    "35-frontend-proxy.yaml",
    "40-flagd.yaml",
    "90-default-deny-all.yaml",
}

BUSINESS_COMPONENTS = {
    "10-quote.yaml": "quote",
    "11-currency.yaml": "currency",
    "12-payment.yaml": "payment",
    "13-email.yaml": "email",
    "14-ad.yaml": "ad",
    "15-image-provider.yaml": "image-provider",
    "16-llm.yaml": "llm",
    "20-product-catalog.yaml": "product-catalog",
    "21-cart.yaml": "cart",
    "22-accounting.yaml": "accounting",
    "23-fraud-detection.yaml": "fraud-detection",
    "30-shipping.yaml": "shipping",
    "31-recommendation.yaml": "recommendation",
    "32-product-reviews.yaml": "product-reviews",
    "33-checkout.yaml": "checkout",
    "34-frontend.yaml": "frontend",
    "35-frontend-proxy.yaml": "frontend-proxy",
    "40-flagd.yaml": "flagd",
}

EXPECTED_EGRESS_COMPONENTS = {
    "quote": {"otel-gateway"},
    "currency": {"otel-gateway"},
    "payment": {"flagd", "otel-gateway"},
    "email": {"flagd", "otel-gateway"},
    "ad": {"flagd", "otel-gateway"},
    "image-provider": {"otel-gateway"},
    "llm": {"flagd"},
    "product-catalog": {"flagd", "otel-gateway"},
    "cart": {"flagd", "otel-gateway"},
    "accounting": {"otel-gateway"},
    "fraud-detection": {"flagd", "otel-gateway"},
    "shipping": {"quote", "otel-gateway"},
    "recommendation": {"product-catalog", "flagd", "otel-gateway"},
    "product-reviews": {"product-catalog", "flagd", "otel-gateway"},
    "checkout": {
        "cart",
        "currency",
        "email",
        "payment",
        "product-catalog",
        "shipping",
        "flagd",
        "otel-gateway",
    },
    "frontend": {
        "ad",
        "cart",
        "checkout",
        "currency",
        "product-catalog",
        "product-reviews",
        "recommendation",
        "shipping",
        "flagd",
        "otel-gateway",
    },
    "frontend-proxy": {"frontend", "image-provider", "flagd", "otel-gateway"},
    "flagd": {"otel-gateway"},
}

PUBLIC_EGRESS_FILES = {
    "06-cloudflared.yaml",
    "07-aiops-engine.yaml",
    "32-product-reviews.yaml",
}


def load_documents(path):
    return [
        document
        for document in yaml.safe_load_all(path.read_text(encoding="utf-8"))
        if document
    ]


def load_policy(filename):
    documents = load_documents(STAGED / filename)
    assert len(documents) == 1, f"{filename} must contain exactly one object"
    policy = documents[0]
    assert policy["kind"] == "NetworkPolicy"
    return policy


def walk(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from walk(value)


def contains_public_cidr(document):
    return any(
        item.get("ipBlock", {}).get("cidr") == "0.0.0.0/0"
        for item in walk(document)
    )


def selector_components(selector):
    components = set()
    labels = selector.get("matchLabels", {})
    component = labels.get("app.kubernetes.io/component")
    if component:
        components.add(component)
    for expression in selector.get("matchExpressions", []):
        if expression.get("key") == "app.kubernetes.io/component":
            components.update(expression.get("values", []))
    return components


def peer_components(peer):
    return selector_components(peer.get("podSelector", {}))


def egress_components(policy):
    components = set()
    for rule in policy["spec"].get("egress", []):
        for peer in rule.get("to", []):
            components.update(peer_components(peer))
    return components


def ports_for_egress_destination(policy, destination):
    ports = set()
    for rule in policy["spec"].get("egress", []):
        if any(destination in peer_components(peer) for peer in rule.get("to", [])):
            ports.update(port["port"] for port in rule.get("ports", []))
    return ports


def test_staged_inventory_is_one_policy_per_file():
    actual = {path.name for path in STAGED.glob("*.yaml")}
    assert actual == EXPECTED_FILES
    for filename in actual:
        policy = load_policy(filename)
        assert policy["metadata"]["namespace"] == "techx-tf3"


def test_all_business_components_are_selected_once():
    selected = {}
    for filename, expected_component in BUSINESS_COMPONENTS.items():
        policy = load_policy(filename)
        selector = policy["spec"]["podSelector"]
        assert selector_components(selector) == {expected_component}
        selected[filename] = expected_component
    assert set(selected.values()) == set(EXPECTED_EGRESS_COMPONENTS)


def test_business_egress_dependency_graph_is_exact():
    for filename, component in BUSINESS_COMPONENTS.items():
        policy = load_policy(filename)
        assert egress_components(policy) == EXPECTED_EGRESS_COMPONENTS[component]


def test_checkout_ports_and_indirect_quote_path_are_exact():
    checkout = load_policy("33-checkout.yaml")
    for destination in {
        "cart",
        "currency",
        "email",
        "payment",
        "product-catalog",
        "shipping",
    }:
        assert ports_for_egress_destination(checkout, destination) == {8080}
    assert ports_for_egress_destination(checkout, "flagd") == {8013}
    assert ports_for_egress_destination(checkout, "otel-gateway") == {4317}
    assert "quote" not in egress_components(checkout)


def test_jaeger_accepts_otel_gateway_grpc_ingest():
    jaeger = load_policy("02-jaeger.yaml")
    matching_ports = set()
    for rule in jaeger["spec"]["ingress"]:
        if any("otel-gateway" in peer_components(peer) for peer in rule.get("from", [])):
            matching_ports.update(port["port"] for port in rule.get("ports", []))
    assert 4317 in matching_ports


def test_every_non_default_egress_policy_has_exact_coredns_rule():
    for filename in EXPECTED_FILES - {"90-default-deny-all.yaml"}:
        policy = load_policy(filename)
        if "Egress" not in policy["spec"].get("policyTypes", []):
            continue
        found = False
        for rule in policy["spec"].get("egress", []):
            for peer in rule.get("to", []):
                namespace = peer.get("namespaceSelector", {}).get("matchLabels", {})
                pod = peer.get("podSelector", {}).get("matchLabels", {})
                if (
                    namespace.get("kubernetes.io/metadata.name") == "kube-system"
                    and pod.get("k8s-app") == "kube-dns"
                ):
                    ports = {
                        (item.get("protocol", "TCP"), item["port"])
                        for item in rule.get("ports", [])
                    }
                    assert ports == {("TCP", 53), ("UDP", 53)}
                    found = True
        assert found, f"{filename} is missing the exact CoreDNS rule"


def test_public_egress_is_blocked_from_promotion_and_never_active():
    staged_public = {
        filename
        for filename in EXPECTED_FILES
        if contains_public_cidr(load_policy(filename))
    }
    assert staged_public == PUBLIC_EGRESS_FILES
    for filename in staged_public:
        annotations = load_policy(filename)["metadata"].get("annotations", {})
        assert annotations.get("mandate-17.techx.io/promotion-blocked") == "true"
        assert annotations.get("mandate-17.techx.io/promotion-blocker")

    for path in INFRA.glob("*.yaml"):
        for document in load_documents(path):
            if document.get("kind") == "NetworkPolicy":
                assert not contains_public_cidr(document), (
                    f"active policy {path.name} must not allow 0.0.0.0/0"
                )


def test_ad_is_the_clusterip_canary_and_aiops_api_use_is_unverified():
    ad_annotations = load_policy("14-ad.yaml")["metadata"]["annotations"]
    assert ad_annotations["mandate-17.techx.io/rollout-role"] == "first-canary"
    assert ad_annotations["mandate-17.techx.io/clusterip-proof"] == (
        "required-before-wider-promotion"
    )
    aiops_annotations = load_policy("07-aiops-engine.yaml")["metadata"]["annotations"]
    assert aiops_annotations["mandate-17.techx.io/kubernetes-api-dependency"] == (
        "unverified"
    )


def test_default_deny_is_empty_and_marked_last():
    policy = load_policy("90-default-deny-all.yaml")
    assert policy["spec"]["podSelector"] == {}
    assert set(policy["spec"]["policyTypes"]) == {"Ingress", "Egress"}
    assert "ingress" not in policy["spec"]
    assert "egress" not in policy["spec"]
    assert policy["metadata"]["annotations"][
        "mandate-17.techx.io/activation-order"
    ] == "last"


def test_argocd_does_not_recurse_into_staging():
    application = yaml.safe_load(
        (REPO / "gitops/apps/infrastructure-app.yaml").read_text(encoding="utf-8")
    )
    source = application["spec"]["source"]
    assert source["path"] == "gitops/infrastructure"
    assert source.get("directory", {}).get("recurse") is not True


def test_rollout_runbook_requires_canary_owner_and_last_default_deny():
    runbook = (STAGED / "README.md").read_text(encoding="utf-8")
    assert runbook.index("14-ad.yaml") < runbook.index("remaining leaf services")
    assert runbook.rindex("90-default-deny-all.yaml") > runbook.index("platform policies")
    assert "ownerReferences" in runbook
    assert "bare Pod is not accepted" in runbook
    assert "promotion-blocked" in runbook
