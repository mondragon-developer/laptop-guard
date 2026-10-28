"""Create a draft once; preserve an existing release and its uploaded assets."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


def ensure_release(repository, tag, artifacts, notes):
    if not re.fullmatch(r"v\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?", tag):
        raise ValueError("Expected a version tag, for example v1.1.0")
    version = tag[1:]
    expected = {f"LaptopGuard-{version}-{target}.zip{suffix}"
                for target in ("windows-x64", "macos-apple-silicon", "macos-intel")
                for suffix in ("", ".sha256")}
    files = {path.name: path for path in Path(artifacts).iterdir() if path.is_file()}
    if not expected.issubset(files):
        raise ValueError(f"Missing release artifacts: {sorted(expected - files.keys())}")
    for name in sorted(expected):
        if name.endswith(".zip"):
            digest = hashlib.sha256(files[name].read_bytes()).hexdigest()
            if files[name + ".sha256"].read_text().split()[0] != digest:
                raise ValueError(f"Checksum mismatch: {name}")
    # List authenticated releases, including drafts. A draft can share the tag
    # of an already published release, so prefer the published one explicitly.
    result = subprocess.run(["gh", "api", "--paginate", "--slurp",
                             f"repos/{repository}/releases?per_page=100"],
                            capture_output=True, text=True, check=True)
    matches = [release for page in json.loads(result.stdout) for release in page
               if release["tag_name"] == tag]
    if matches:
        existing = min(matches, key=lambda release: release["draft"])
        uploaded = {item["name"] for item in existing["assets"]
                    if item["state"] == "uploaded" and item["size"] > 0}
        if not expected.issubset(uploaded):
            raise RuntimeError("Existing release is incomplete; review it without replacing its files")
        print(f"Preserved existing release: {existing['html_url']}")
        return existing["html_url"]
    # A failed API request above stops here; it is never interpreted as absence.
    result = subprocess.run(["gh", "release", "create", tag, "--repo", repository,
                             "--verify-tag", "--draft", "--title", f"Laptop Guard {tag}",
                             "--notes-file", str(notes),
                             *(str(files[name]) for name in sorted(expected))],
                            capture_output=True, text=True, check=True)
    print(result.stdout.strip())
    return result.stdout.strip()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--artifacts", type=Path, default=Path("artifacts"))
    parser.add_argument("--notes", type=Path, default=Path("release/RELEASE-NOTES.md"))
    args = parser.parse_args()
    ensure_release(args.repo, args.tag, args.artifacts, args.notes)
