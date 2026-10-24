#!/usr/bin/env bash
# Roll the training-workbench chart, under the cluster's roll lock.
#
#   usage: KUBE_CONTEXT=<context> scripts/roll.sh <values file> [extra helm args ...]
#   env:   NS (default training), RELEASE (default training-workbench),
#          EXPECTED_MIN (default 20), the lock's expected_end from now,
#          GATE_URL (optional, scheme://host): /healthz and / must answer 200 there,
#          GATE_INSECURE=1 accepts a self-signed cert on it (sandbox hosts, until cert-manager).
#
# THE LOCK. Before any helm upgrade the roller creates ConfigMap sandbox/roll-lock
# {lane, started, expected_end}. Every roll script refuses to start while it exists and is
# younger than 90 minutes, and the roller deletes it when the gates pass. Why: prime's
# ingests run in the doc-tools code location, so a doc-tools roll during an iagent prime
# kills the prime. This chart touches neither, but it rolls on the same cluster under the
# same rule.
#
# A failed gate leaves the lock in place on purpose. The next roller sees who broke what,
# and the 90-minute rule releases it if nobody comes back.
set -uo pipefail

LANE="training-consolidation-workbench/lane/wb"
LOCK_NS="sandbox"
LOCK="roll-lock"
MAX_AGE_S=$((90 * 60))
NS="${NS:-training}"
RELEASE="${RELEASE:-training-workbench}"
EXPECTED_MIN="${EXPECTED_MIN:-20}"
CHART="$(cd "$(dirname "$0")/.." && pwd)/charts/training-workbench"

values="${1:?usage: KUBE_CONTEXT=<context> scripts/roll.sh <values file> [helm args ...]}"
shift
: "${KUBE_CONTEXT:?set KUBE_CONTEXT}"
kc() { kubectl --context "$KUBE_CONTEXT" "$@"; }

# 1. Refuse while a lock younger than 90 minutes exists; clear a stale one.
created=$(kc -n "$LOCK_NS" get configmap "$LOCK" -o jsonpath='{.metadata.creationTimestamp}' 2>/dev/null)
if [ -n "$created" ]; then
  age=$(( $(date -u +%s) - $(date -u -d "$created" +%s) ))
  holder=$(kc -n "$LOCK_NS" get configmap "$LOCK" -o jsonpath='{.data.lane} until {.data.expected_end}')
  if [ "$age" -lt "$MAX_AGE_S" ]; then
    echo "REFUSED: $LOCK_NS/$LOCK held by $holder, age ${age}s (< ${MAX_AGE_S}s)" >&2
    exit 2
  fi
  echo "stale lock ($holder, age ${age}s): deleting it"
  kc -n "$LOCK_NS" delete configmap "$LOCK" >/dev/null || exit 2
fi

# 2. Take it. create fails if another roller got there first, so the check above can't race.
started=$(date -u +%Y-%m-%dT%H:%M:%SZ)
expected_end=$(date -u -d "+${EXPECTED_MIN} minutes" +%Y-%m-%dT%H:%M:%SZ)
if ! kc -n "$LOCK_NS" create configmap "$LOCK" --from-literal=lane="$LANE" \
     --from-literal=started="$started" --from-literal=expected_end="$expected_end" >/dev/null; then
  echo "REFUSED: could not create $LOCK_NS/$LOCK (another roller took it?)" >&2
  exit 2
fi
echo "lock taken: $LANE, $started to $expected_end"

# 3. Roll. --wait makes helm the readiness gate for both Deployments.
if ! helm --kube-context "$KUBE_CONTEXT" upgrade --install "$RELEASE" "$CHART" -n "$NS" \
     -f "$values" --wait --timeout 10m "$@"; then
  echo "GATE FAILED: helm upgrade; lock left in place" >&2
  exit 1
fi

# 4. Gates through the ingress, when the caller names the URL.
if [ -n "${GATE_URL:-}" ]; then
  insecure=()
  [ "${GATE_INSECURE:-}" = 1 ] && insecure=(-k)
  for path in /healthz /; do
    # helm --wait returns when the new pod is Ready; the ingress can still route to the
    # terminating old one for a few seconds (a 502), so give it up to a minute.
    for _ in 1 2 3 4 5 6 7 8 9 10 11 12; do
      code=$(curl -s ${insecure[@]+"${insecure[@]}"} -o /dev/null -w '%{http_code}' --max-time 15 "${GATE_URL%/}$path")
      [ "$code" = 200 ] && break
      sleep 5
    done
    echo "gate ${path}: $code"
    if [ "$code" != 200 ]; then
      echo "GATE FAILED: ${path} answered $code; lock left in place" >&2
      exit 1
    fi
  done
fi

# 5. Gates passed: release.
kc -n "$LOCK_NS" delete configmap "$LOCK" >/dev/null && echo "lock released"
