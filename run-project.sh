#!/bin/bash
# Runs the EISOP Nullness Checker over one corpus project under one or more arms, and summarizes
# the diagnostics per arm.
#
#   ./run-project.sh <name> [arm...]        (default arms: all of them)
#
# Environment:
#   EISOP_VERSION   checker version to resolve (default 3.49.5-eisop2-SNAPSHOT, from mavenLocal)
#   JDK_HOME_<n>    JDK for manifest jdk column <n>; otherwise /usr/libexec/java_home -v <n>
#   WORK_DIR        where projects are cloned (default ./work)
#   RESULTS_DIR     where results go (default ./results)

set -euo pipefail

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
WORK_DIR="${WORK_DIR:-$HERE/work}"
RESULTS_DIR="${RESULTS_DIR:-$HERE/results}"
export EISOP_VERSION="${EISOP_VERSION:-3.49.5-eisop2-SNAPSHOT}"

# An arm is a named checker option set.  The mode-derived arms must spell the mode's options out:
# every option -Amode=jspecify adds is a presence flag with no negative form, so it cannot be
# turned back off when the mode itself is passed.
arm_args() {
  case "$1" in
    jspecify)             echo "-Amode=jspecify" ;;
    jspecify-nolocations) echo "-AonlyAnnotatedFor -AjspecifyNullMarkedAlias=true -AassumeInitialized -AassumeKeyFor" ;;
    jspecify-bytecode)    echo "-Amode=jspecify -AuseConservativeDefaultsForUncheckedCode=bytecode" ;;
    *) echo "unknown arm: $1" >&2; exit 2 ;;
  esac
}
ALL_ARMS=(jspecify jspecify-nolocations jspecify-bytecode)

name="${1:?usage: run-project.sh <name> [arm...]}"
shift
arms=("$@")
[ ${#arms[@]} -eq 0 ] && arms=("${ALL_ARMS[@]}")

row="$(awk -F'\t' -v n="$name" 'NR > 1 && $1 == n' "$HERE/corpus.tsv")"
[ -n "$row" ] || { echo "no project '$name' in corpus.tsv" >&2; exit 2; }
IFS=$'\t' read -r _ repo sha build tasks jdk status notes <<< "$row"
[ "$build" = gradle ] || { echo "$name: build system '$build' is not supported yet" >&2; exit 3; }

jdk_var="JDK_HOME_$jdk"
java_home="${!jdk_var:-$(/usr/libexec/java_home -v "$jdk" 2>/dev/null || true)}"
[ -n "$java_home" ] || { echo "no JDK $jdk found; set $jdk_var" >&2; exit 3; }

src="$WORK_DIR/$name"
if [ "$(git -C "$src" rev-parse HEAD 2>/dev/null || true)" != "$sha" ]; then
  rm -rf "$src"
  mkdir -p "$src"
  git -C "$src" init -q
  git -C "$src" remote add origin "https://github.com/$repo"
  git -C "$src" fetch -q --depth 1 origin "$sha"
  git -C "$src" checkout -q FETCH_HEAD
fi

# Canaries make "no findings" trustworthy.  The marked one sits in a @NullMarked package and must
# be reported; the unmarked one sits in a new package of the same source root and, under
# -AonlyAnnotatedFor, must not be.  summarize.py reports both and leaves them out of the counts.
marked_info="$(grep -rlE '@(org\.jspecify\.annotations\.)?NullMarked' --include=package-info.java "$src" \
               | grep '/src/main/java/' | sort | head -1 || true)"
canaries=()
if [ -n "$marked_info" ]; then
  pkg="$(sed -nE 's/^[[:space:]]*package[[:space:]]+([A-Za-z0-9_.]+)[[:space:]]*;.*/\1/p' "$marked_info" | head -1)"
  pkg_dir="$(dirname "$marked_info")"
  src_root="${pkg_dir%/"${pkg//.//}"}"
  canary_body='final class EisopCorpusCanary {
  static String canary(@org.jspecify.annotations.Nullable String s) {
    return s;
  }
}'
  mkdir -p "$src_root/eisopcorpus/unmarked"
  printf 'package %s;\n\n%s\n' "$pkg" "$canary_body" > "$pkg_dir/EisopCorpusCanary.java"
  printf 'package eisopcorpus.unmarked;\n\n%s\n' "$canary_body" > "$src_root/eisopcorpus/unmarked/EisopCorpusCanary.java"
  canaries=("$pkg_dir/EisopCorpusCanary.java" "$src_root/eisopcorpus")
fi
cleanup() { [ ${#canaries[@]} -eq 0 ] || rm -rf "${canaries[@]}"; }
trap cleanup EXIT

for arm in "${arms[@]}"; do
  out="$RESULTS_DIR/$name/$arm"
  mkdir -p "$out"
  export EISOP_ARGS="$(arm_args "$arm")"
  echo "== $name @ ${sha:0:12} arm=$arm ($EISOP_ARGS)"
  set +e
  # CI is unset because several projects hide Error Prone warnings (and so NullAway's, once
  # demoted to warnings) when it is present.
  (cd "$src" && env -u CI JAVA_HOME="$java_home" ./gradlew \
      --init-script "$HERE/eisop-nullness.init.gradle" \
      --no-configuration-cache --no-build-cache --no-parallel --continue --console=plain \
      $tasks) > "$out/build.log" 2>&1
  status=$?
  set -e
  cat > "$out/meta.tsv" <<META
project	$name
repo	$repo
sha	$sha
arm	$arm
args	$EISOP_ARGS
eisop_version	$EISOP_VERSION
java_home	$java_home
gradle_exit	$status
date	$(date -u +%Y-%m-%dT%H:%M:%SZ)
META
  python3 "$HERE/summarize.py" "$src" "$out" || failed=1
done
exit "${failed:-0}"
