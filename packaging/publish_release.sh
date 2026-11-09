#!/usr/bin/env bash
# Publish tested, tagged Windows and Android builds as ONE new release in the public downloads repository.
#
# Run by the release job of .github/workflows/desktop-probe.yml, from the folder that holds the
# verified pair (the ZIP, APK, SHA256SUMS, BUILD.json and BUILD_INFO.txt).
#
# Never replaces anything: if the release or its tag already exists in the downloads repository the
# job fails. The files are uploaded to a draft first, downloaded back and compared byte for byte, and
# only then published. Needs:
#   GH_TOKEN        fine-grained token with Contents: read and write on DOWNLOADS_REPO
#   DOWNLOADS_REPO  owner/name of the public downloads repository
#   TAG             the release tag, e.g. v2.0.0 (already checked against the source version)
#   ZIP             the ZIP's file name, e.g. Lightning-v2.0.0-Windows-x64.zip
#   APK             the signed phone APK's file name, from BUILD.json
#   UPDATE_KEYS     optional: another pinned-keys file (tests only)
#   PYTHON          optional: the Python that has `cryptography` (default python3)
# The folder must also hold UPDATE.json and UPDATE.json.sig (packaging/update_manifest.py sign): the signed
# manifest the in-app updater trusts. They are re-verified here and uploaded beside the others.
set -euo pipefail

fail() { echo "::error::$*"; exit 1; }

: "${DOWNLOADS_REPO:?}" "${TAG:?}" "${ZIP:?}" "${APK:?}"
[[ -n "${GH_TOKEN:-}" ]] || fail "The LIGHTNING_DOWNLOADS_TOKEN secret is not set. Create a fine-grained personal access token with Contents: read and write on ${DOWNLOADS_REPO} only, add it to this repository as the Actions secret LIGHTNING_DOWNLOADS_TOKEN, then re-run this job. Nothing was published."
[[ "$ZIP" =~ ^Lightning-v[0-9A-Za-z.+-]+-Windows-x64\.zip$ ]] || fail "Unexpected ZIP name: $ZIP"
[[ "$ZIP" == "Lightning-${TAG}-Windows-x64.zip" ]] || fail "The ZIP $ZIP was not built as release $TAG (a development build cannot be published)."
[[ "$APK" =~ ^Lightning-[0-9A-Za-z.+-]+\.apk$ ]] || fail "Unexpected APK name: $APK"

for file in "$ZIP" "$APK" SHA256SUMS BUILD.json BUILD_INFO.txt UPDATE.json UPDATE.json.sig; do
  [[ -f "$file" ]] || fail "The build artifact has no $file."
done
[[ $(wc -l < SHA256SUMS) -eq 2 ]] || fail "SHA256SUMS must name exactly the ZIP and APK."
grep -Fqx "$(sha256sum "$ZIP")" SHA256SUMS || fail "SHA256SUMS does not describe $ZIP."
grep -Fqx "$(sha256sum "$APK")" SHA256SUMS || fail "SHA256SUMS does not describe $APK."
sha256sum --check --strict SHA256SUMS || fail "The builds do not match SHA256SUMS."
grep -qx "Build: release ${TAG}" BUILD_INFO.txt || fail "BUILD_INFO.txt does not say this is release ${TAG}."
jq -e --arg zip "$ZIP" --arg apk "$APK" --arg commit "$(sed -n 's/^Commit: //p' BUILD_INFO.txt)" \
  '.windows.file == $zip and .android.file == $apk and .commit == $commit and
   .android.application_id == "org.lightning.app" and .android.debuggable == false and
   (.android.certificate_sha256 | type == "string" and length > 0)' BUILD.json >/dev/null \
  || fail "BUILD.json does not identify this tested pair and its signed Lightning app."
"${PYTHON:-python3}" "$(dirname "${BASH_SOURCE[0]}")/update_manifest.py" verify --dir . --tag "$TAG" --zip "$ZIP" ${UPDATE_KEYS:+--keys "$UPDATE_KEYS"} \
  || fail "UPDATE.json and its signature do not verify for $TAG and $ZIP. Nothing was published."
zip_sha=$(sha256sum "$ZIP" | cut -d' ' -f1)
apk_sha=$(sha256sum "$APK" | cut -d' ' -f1)

# The token must reach the downloads repository before anything else is decided.
gh api "repos/${DOWNLOADS_REPO}" --jq .full_name >/dev/null \
  || fail "The token cannot read ${DOWNLOADS_REPO}. Check that LIGHTNING_DOWNLOADS_TOKEN has Contents: read and write on it."

# Prints exists or missing. Any other answer (a network error, rate limit, a token without access)
# stops the job with gh's own message, never mistaken for "already exists".
lookup() {
  local out
  if out=$(gh api "$1" 2>&1); then echo exists; return; fi
  if [[ "$out" == *"HTTP 404"* ]]; then echo missing; return; fi
  echo "$out" >&2
  echo error
}
state=$(lookup "repos/${DOWNLOADS_REPO}/releases/tags/${TAG}")
[[ "$state" == error ]] && fail "Could not check whether ${DOWNLOADS_REPO} has a release ${TAG} (see the message above). Nothing was published."
[[ "$state" == missing ]] || fail "${DOWNLOADS_REPO} already has a release ${TAG}. Published versions are never replaced: bump the version for a new build."
state=$(lookup "repos/${DOWNLOADS_REPO}/git/ref/tags/${TAG}")
[[ "$state" == error ]] && fail "Could not check whether ${DOWNLOADS_REPO} has a tag ${TAG} (see the message above). Nothing was published."
[[ "$state" == missing ]] || fail "${DOWNLOADS_REPO} already has a tag ${TAG}. Published versions are never replaced: bump the version for a new build."

version="${TAG#v}"
pretty=$(sed -E 's/-rc\.([0-9]+)$/ release candidate \1/' <<<"$version")
title="Lightning ${pretty} for Windows and Android"
# A draft is created under this name and renamed in the same call that publishes it, so a published
# release never carries it. GitHub turns a published release whose tag was deleted back into a draft
# with its real name: that draft is never removed here.
draft_name="${title} (unpublished draft)"
drafts=$(gh api --paginate "repos/${DOWNLOADS_REPO}/releases" \
           --jq ".[] | select(.draft and .tag_name == \"${TAG}\") | [.id, .name] | @tsv")
while IFS=$'\t' read -r id name; do
  [[ -n "$id" ]] || continue
  [[ "$name" == "$draft_name" ]] || fail "${DOWNLOADS_REPO} has a draft ${TAG} (\"${name}\") that this job did not leave behind: it may be a published release whose tag was deleted. Check it by hand; nothing was changed."
  echo "Removing unpublished draft ${id} left by an earlier attempt."
  gh api -X DELETE "repos/${DOWNLOADS_REPO}/releases/${id}" >/dev/null
done <<<"$drafts"
prerelease=false
[[ "$version" == *-* ]] && prerelease=true
commit=$(sed -n 's/^Commit: //p' BUILD_INFO.txt)
run=$(sed -n 's/^Run: //p' BUILD_INFO.txt)

notes=$(mktemp)
{
  echo "Lightning ${pretty} for Windows (x64) and Android (arm64), built from the same Lightning source commit ${commit} (${run})."
  echo
  echo "PC: download **${ZIP}**, extract it into a new folder, then run \`Lightning\\Lightning.exe\`."
  echo "The Microsoft Edge WebView2 Runtime is required; Python is not."
  echo "Phone: download **${APK}** on Android and install it. Pair it with this release's PC build."
  echo
  if [[ "$prerelease" == true ]]; then
    echo "You may use sample or real data; keep an independent backup. The Windows app is not code-signed and Windows may warn before the first start."
  else
    echo "The app is not code-signed, so Windows may warn before the first start."
  fi
  echo
  echo "SHA-256 of ${ZIP}: \`${zip_sha}\`. SHA-256 of ${APK}: \`${apk_sha}\`. Both are in SHA256SUMS."
} >"$notes"

release_json=$(gh api -X POST "repos/${DOWNLOADS_REPO}/releases" \
  -f tag_name="$TAG" -f target_commitish=main -f name="$draft_name" \
  -F body=@"$notes" -F draft=true -F prerelease="$prerelease")
release_id=$(jq -r .id <<<"$release_json")
upload_url="https://uploads.github.com/repos/${DOWNLOADS_REPO}/releases/${release_id}/assets"
echo "Created draft release ${release_id}."

for file in "$ZIP" "$APK" SHA256SUMS BUILD.json UPDATE.json UPDATE.json.sig; do
  type=application/octet-stream
  [[ "$file" == *.zip ]] && type=application/zip
  [[ "$file" == *.apk ]] && type=application/vnd.android.package-archive
  [[ "$file" == *.json ]] && type=application/json
  [[ "$file" == *.sig ]] && type=text/plain
  gh api -X POST "${upload_url}?name=${file}" -H "Content-Type: ${type}" --input "$file" --jq .name >/dev/null
  echo "Uploaded ${file}."
done

# Download every asset back from the draft and compare it with what was tested.
check_dir=$(mktemp -d)
mapfile -t assets < <(gh api "repos/${DOWNLOADS_REPO}/releases/${release_id}/assets" --jq '.[] | "\(.id) \(.name)"')
[[ ${#assets[@]} -eq 6 ]] || fail "The draft has ${#assets[@]} files instead of 6."
for entry in "${assets[@]}"; do
  id=${entry%% *}; name=${entry#* }
  gh api -H "Accept: application/octet-stream" "repos/${DOWNLOADS_REPO}/releases/assets/${id}" >"${check_dir}/${name}"
  cmp -s "${check_dir}/${name}" "$name" || fail "The uploaded ${name} differs from the tested file. The draft was left unpublished."
done
echo "All six files read back identical to the tested pair."

published=$(gh api -X PATCH "repos/${DOWNLOADS_REPO}/releases/${release_id}" -f name="$title" -F draft=false)
[[ $(jq -r .draft <<<"$published") == false ]] || fail "The release did not publish."
[[ $(jq -r .tag_name <<<"$published") == "$TAG" ]] || fail "The published release has the wrong tag."
[[ $(jq -r .name <<<"$published") == "$title" ]] || fail "The published release kept its draft name."
url=$(jq -r .html_url <<<"$published")
echo "Published ${url}"
if [[ $(jq -r '.immutable // false' <<<"$published") != true ]]; then
  echo "::warning::${DOWNLOADS_REPO} does not make releases immutable. Turn on release immutability in its Settings so a published version can never be changed."
fi
{
  echo "### Released Lightning ${pretty}"
  echo
  echo "- Download page: ${url}"
  echo "- ZIP: ${ZIP}"
  echo "- APK: ${APK}"
  echo "- SHA-256 (PC): \`${zip_sha}\`"
  echo "- SHA-256 (Phone): \`${apk_sha}\`"
} >>"${GITHUB_STEP_SUMMARY:-/dev/null}"
