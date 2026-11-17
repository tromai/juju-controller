#!/usr/bin/env bash
# Checks that a Kubernetes controller pod runs the jujud-operator image that
# CI built and imported into the cluster, rather than one it pulled from a
# registry.
#
# Usage: check-controller-image.sh <namespace> <image-tar>
#
#   namespace  The controller's namespace, e.g. controller-k8s.
#   image-tar  The `docker save` archive that was imported into the cluster.
#
# KUBECTL is the kubectl command to run (word-split), e.g. "sudo k8s kubectl".
#
# Every container of controller-0 that runs a jujud-operator image must run
# the image of the archive, identified by its config digest (the image ID,
# which is what containerd reports for an image imported with `ctr`) or its
# manifest digest (reported instead when the image has a repo digest). And
# the kubelet must never have pulled it.
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 <namespace> <image-tar>" >&2
  exit 2
fi
NS=$1
TAR=$2
read -r -a KUBECTL_CMD <<< "${KUBECTL:-kubectl}"

# The image name and digests, from the archive's OCI index and Docker
# manifest.
read -r REF MANIFEST_DIGEST CONFIG_DIGEST < <(python3 - "$TAR" <<'EOF'
import json
import os
import sys
import tarfile

with tarfile.open(sys.argv[1]) as tar:
    index = json.load(tar.extractfile("index.json"))
    manifest = json.load(tar.extractfile("manifest.json"))
if len(index["manifests"]) != 1 or len(manifest) != 1:
    sys.exit("expected exactly one image in the archive")
ref = manifest[0]["RepoTags"][0]
manifest_digest = index["manifests"][0]["digest"]
# "blobs/sha256/<hex>" (Docker >= 25) or "<hex>.json" (older Docker).
config = os.path.basename(manifest[0]["Config"]).removesuffix(".json")
print(ref, manifest_digest, f"sha256:{config}")
EOF
)
echo "Imported image: $REF"
echo "  manifest digest: $MANIFEST_DIGEST"
echo "  config digest:   $CONFIG_DIGEST"

JSONPATH='{range .status.initContainerStatuses[*]}'
JSONPATH+='{.name}{"\t"}{.image}{"\t"}{.imageID}{"\n"}{end}'
JSONPATH+='{range .status.containerStatuses[*]}'
JSONPATH+='{.name}{"\t"}{.image}{"\t"}{.imageID}{"\n"}{end}'
STATUSES=$("${KUBECTL_CMD[@]}" -n "$NS" get pod controller-0 \
  -o jsonpath="$JSONPATH")

failed=0
checked=0
while IFS=$'\t' read -r name image image_id; do
  [[ -n "$name" ]] || continue
  echo "$name: $image ($image_id)"
  [[ "$image" == */jujud-operator:* ]] || continue
  checked=$((checked + 1))
  if [[ "$image" != "$REF" ]]; then
    echo "::error::$name runs $image, not the imported $REF"
    failed=1
  elif [[ "$image_id" != "$CONFIG_DIGEST" &&
          "$image_id" != *"@$MANIFEST_DIGEST" ]]; then
    echo "::error::$name runs $image_id, not the imported image" \
      "($CONFIG_DIGEST / $MANIFEST_DIGEST)"
    failed=1
  fi
done <<< "$STATUSES"

if [[ $checked -eq 0 ]]; then
  echo "::error::No container of controller-0 runs a jujud-operator image"
  failed=1
fi

# With imagePullPolicy IfNotPresent, the kubelet only pulls an image that
# isn't present on the node: any pull of the jujud-operator image means the
# imported one wasn't used.
PULLS=$("${KUBECTL_CMD[@]}" -n "$NS" get events \
  --field-selector involvedObject.name=controller-0,reason=Pulling \
  -o jsonpath='{range .items[*]}{.message}{"\n"}{end}' \
  | grep -F "/jujud-operator:" || true)
if [[ -n "$PULLS" ]]; then
  echo "::error::The kubelet pulled the jujud-operator image: $PULLS"
  failed=1
fi

exit "$failed"
