#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="${NAMESPACE:-techx-tf3}"
POD_NAME="${POD_NAME:-flagdcheck}"
CURL_IMAGE="${CURL_IMAGE:-curlimages/curl:8.11.1}"
FLAGD_OFREP_URL="${FLAGD_OFREP_URL:-http://flagd:8016/ofrep/v1/evaluate/flags}"
CONTEXT_JSON="${CONTEXT_JSON:-{\"context\":{}}}"

cleanup() {
  kubectl -n "$NAMESPACE" delete pod "$POD_NAME" --ignore-not-found=true --wait=false >/dev/null 2>&1 || true
}

cleanup
trap cleanup EXIT

manifest="$(mktemp)"
trap 'rm -f "$manifest"; cleanup' EXIT

cat > "$manifest" <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: ${POD_NAME}
  namespace: ${NAMESPACE}
  labels:
    app.kubernetes.io/name: flagdcheck
    app.kubernetes.io/part-of: techx-diagnostics
    app.kubernetes.io/component: flagd-readonly-probe
spec:
  restartPolicy: Never
  automountServiceAccountToken: false
  securityContext:
    runAsNonRoot: true
    runAsUser: 65532
    runAsGroup: 65532
    seccompProfile:
      type: RuntimeDefault
  containers:
    - name: flagdcheck
      image: ${CURL_IMAGE}
      imagePullPolicy: IfNotPresent
      command:
        - curl
      args:
        - "-fsS"
        - "-X"
        - "POST"
        - "${FLAGD_OFREP_URL}"
        - "-H"
        - "Content-Type: application/json"
        - "-d"
        - '${CONTEXT_JSON}'
      securityContext:
        runAsNonRoot: true
        runAsUser: 65532
        runAsGroup: 65532
        allowPrivilegeEscalation: false
        capabilities:
          drop:
            - ALL
        readOnlyRootFilesystem: true
      resources:
        requests:
          cpu: 10m
          memory: 32Mi
        limits:
          cpu: 100m
          memory: 128Mi
EOF

kubectl apply -f "$manifest" >/dev/null
kubectl -n "$NAMESPACE" wait --for=condition=PodScheduled "pod/$POD_NAME" --timeout=30s >/dev/null

phase=""
for _ in $(seq 1 30); do
  phase="$(kubectl -n "$NAMESPACE" get pod "$POD_NAME" -o jsonpath='{.status.phase}' 2>/dev/null || true)"
  if [ "$phase" = "Succeeded" ] || [ "$phase" = "Failed" ]; then
    break
  fi
  sleep 1
done

kubectl -n "$NAMESPACE" logs "$POD_NAME"

if [ "$phase" != "Succeeded" ]; then
  echo "flagdcheck pod finished with phase: ${phase:-unknown}" >&2
  exit 1
fi
