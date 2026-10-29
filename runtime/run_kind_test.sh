#!/usr/bin/env bash
# Runtime proof on a disposable kind cluster: does the model-patched manifest still do its job?
# Uses only synthetic data (a marker file written by a seeder pod into the kind node's /var/bg-demo).
set -euo pipefail
cd "$(dirname "$0")"
NS=bg-runtime
kubectl create namespace "$NS" --dry-run=client -o yaml | kubectl apply -f -

# 1. Seed the node-side file through a short-lived pod (hostPath on a throwaway kind node).
kubectl apply -n "$NS" -f - <<'YAML'
apiVersion: v1
kind: Pod
metadata: {name: bg-seeder}
spec:
  restartPolicy: Never
  containers:
    - name: seed
      image: busybox:1.36.1
      command: ["sh","-c","echo 'BG_SENTINEL line from the node' > /seed/app.log"]
      volumeMounts: [{name: seed, mountPath: /seed}]
  volumes:
    - name: seed
      hostPath: {path: /var/bg-demo, type: DirectoryOrCreate}
YAML
kubectl wait -n "$NS" --for=jsonpath='{.status.phase}'=Succeeded pod/bg-seeder --timeout=120s

result_for () {  # $1 = label, $2 = manifest
  kubectl apply -f "$2" >/dev/null
  kubectl rollout status -n "$NS" deploy/bg-collector --timeout=180s >/dev/null
  sleep 8
  kubectl wait -n "$NS" --for=condition=Ready pod -l app=bg-collector --timeout=120s >/dev/null
  local out; out=$(kubectl logs -n "$NS" -l app=bg-collector --tail=20)
  if grep -q COLLECTED <<<"$out" && ! grep -q NOTHING_TO_COLLECT <<<"$out"; then echo COLLECTED; else echo NOTHING_TO_COLLECT; fi
  echo "--- logs ($1) ---" >&2; echo "$out" | sort | uniq -c >&2
  kubectl delete -f "$2" --wait=true >/dev/null
  kubectl wait -n "$NS" --for=delete pod -l app=bg-collector --timeout=120s >/dev/null 2>&1 || true
}

ORIG=$(result_for original collector.yaml)
PATCHED=$(result_for patched collector.patched.yaml)
echo "original=$ORIG patched=$PATCHED"
printf '{"original":"%s","model_patched":"%s","blastguard_release":"%s"}\n' "$ORIG" "$PATCHED" \
  "$(python3 -c "import json;print(json.load(open('collector.evidence.json'))['release'])")" > runtime-result.json
cat runtime-result.json
[ "$ORIG" = COLLECTED ] && [ "$PATCHED" = NOTHING_TO_COLLECT ]
