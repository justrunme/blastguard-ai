#!/usr/bin/env sh
# Installs kubeconform and kube-linter static binaries into ./bin (optional validators).
set -eu
cd "$(dirname "$0")/.."
mkdir -p bin
curl -fsSL https://github.com/yannh/kubeconform/releases/download/v0.8.0/kubeconform-linux-amd64.tar.gz | tar xz -C bin kubeconform
curl -fsSL https://github.com/stackrox/kube-linter/releases/download/v0.8.3/kube-linter-linux.tar.gz | tar xz -C bin kube-linter
bin/kubeconform -v && bin/kube-linter version
