#!/bin/zsh
# Read the demo credential directly from the terminal.
set -e
umask 077
read -rs 'pharos_key?Paste the xAI API key and press Return: '
print
if [[ -z "$pharos_key" ]]; then
  print -u2 'No API key entered.'
  exit 1
fi
repo_root=${0:A:h:h}
key_file=$(mktemp "$repo_root/.xai-key.XXXXXXXX")
trap 'rm -f -- "$key_file"' EXIT
print -r -- "$pharos_key" > "$key_file"
unset pharos_key
mv -f -- "$key_file" "$repo_root/.xai-key"
print 'Voice key saved locally. Restart the preview to enable recording.'
