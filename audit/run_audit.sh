#!/usr/bin/env bash
# Post-hoc audit of blind-suite REVIEW_REQUIRED calls (b02, b03, b05) on a disposable kind cluster.
# Synthetic data only. Writes audit/audit-result.json and prints evidence logs.
set -uo pipefail
cd "$(dirname "$0")"
M=manifests
OUT=audit-result.json
echo '{}' > "$OUT"
put () { jq --arg k "$1" --argjson v "$2" '.[$k]=$v' "$OUT" > "$OUT.tmp" && mv "$OUT.tmp" "$OUT"; }

kubectl apply -f $M/support.yaml

# ---- b03: nginx-unprivileged; the reloader sidecar image is fictional, so we judge the nginx container only.
for f in $M/b03-*.yaml; do
  v=$(basename "$f" .yaml)
  echo "===== $v"
  kubectl apply -f "$f"
  sleep 60
  pod=$(kubectl get pod -n web -l app=edge-proxy -o jsonpath='{.items[0].metadata.name}')
  st=$(kubectl get pod -n web "$pod" -o json | jq -c '[.status.containerStatuses[] | {name, ready, restartCount, state, lastState}]')
  ip=$(kubectl get pod -n web "$pod" -o jsonpath='{.status.podIP}')
  http=$(kubectl run -n web probe-$RANDOM --rm -i --restart=Never --image=busybox:1.36.1 -- \
           wget -qO- -T 5 "http://$ip:8080/" 2>&1 | head -3 | tr -d '\r' || true)
  logs=$(kubectl logs -n web "$pod" -c nginx --tail=15 2>&1; echo '--- previous ---'; kubectl logs -n web "$pod" -c nginx --previous --tail=15 2>&1)
  echo "$st" | jq .; echo "http: $http"; echo "$logs"
  put "b03/$v" "$(jq -n --argjson s "$st" --arg h "$http" --arg l "$logs" \
     '{containers:$s, http_get_8080:$h, nginx_logs:$l, nginx_serving:($h|test("AUDIT_OK"))}')"
  kubectl delete -f "$f" --wait=true
  kubectl wait -n web --for=delete pod -l app=edge-proxy --timeout=90s || true
done

# ---- b05: kubectl janitor Job; does `kubectl delete pods --field-selector=status.phase==Succeeded -A` work?
for f in $M/b05-*.job.yaml; do
  v=$(basename "$f" .job.yaml)
  echo "===== $v"
  kubectl run -n seed seed-pod --restart=Never --image=busybox:1.36.1 -- true
  kubectl wait -n seed --for=jsonpath='{.status.phase}'=Succeeded pod/seed-pod --timeout=120s
  kubectl apply -f "$f"
  job=$(yq -r .metadata.name "$f" 2>/dev/null || grep -m1 '  name:' "$f" | awk '{print $2}')
  kubectl wait -n ops --for=condition=complete job/"$job" --timeout=150s & a=$!
  kubectl wait -n ops --for=condition=failed job/"$job" --timeout=150s & b=$!
  wait -n $a $b; kill $a $b 2>/dev/null
  jst=$(kubectl get job -n ops "$job" -o json | jq -c '{succeeded:(.status.succeeded//0), failed:(.status.failed//0)}')
  logs=$(kubectl logs -n ops job/"$job" --tail=20 2>&1)
  seed=$(kubectl get pod -n seed seed-pod -o name 2>/dev/null || echo deleted)
  echo "$jst"; echo "seed: $seed"; echo "$logs"
  put "b05/$v" "$(jq -n --argjson j "$jst" --arg s "$seed" --arg l "$logs" \
     '{job:$j, seed_pod:$s, logs:$l, janitor_worked:($j.succeeded>0 and $s=="deleted")}')"
  kubectl delete job -n ops "$job" --wait=true
  kubectl delete pod -n seed seed-pod --ignore-not-found --wait=true
done

# ---- b02: does registry.example.com/ledger-api serve any of the tags? (HTTP registry API + kubelet pull)
for t in latest v1.2.3 v1.0.0; do
  code=$(curl -s -m 15 -o /dev/null -w '%{http_code}' -H 'Accept: application/vnd.oci.image.index.v1+json,application/vnd.docker.distribution.manifest.v2+json' \
         "https://registry.example.com/v2/ledger-api/manifests/$t" 2>&1); rc=$?
  kubectl run -n seed pull-$t --restart=Never --image=registry.example.com/ledger-api:$t >/dev/null
  sleep 40
  ev=$(kubectl get events -n seed --field-selector involvedObject.name=pull-$t -o json | jq -r '[.items[].message] | map(select(test("ull"))) | .[0:3] | join(" | ")')
  wr=$(kubectl get pod -n seed pull-$t -o jsonpath='{.status.containerStatuses[0].state.waiting.reason}')
  echo "b02 $t: http=$code curl_rc=$rc waiting=$wr events=$ev"
  put "b02/$t" "$(jq -n --arg c "$code" --arg r "$rc" --arg w "$wr" --arg e "$ev" '{registry_http:$c, curl_rc:$r, pod_waiting_reason:$w, pull_events:$e}')"
  kubectl delete pod -n seed pull-$t --wait=false
done

jq . "$OUT"
