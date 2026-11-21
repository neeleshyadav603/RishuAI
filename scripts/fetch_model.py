"""Download Rishu's offline model file for the installer (CI), checked by size and SHA-256.

Which model: config/models.yaml -> local_model.choices.<choice> (repo, preferred
quantisation); the file is chosen like the app does (rishu_core.llm.local.pick_file).
Usage: python scripts/fetch_model.py --choice small --out dist/rishu-core/local-llm/models
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

import httpx
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from rishu_core.llm.local import pick_file


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--choice", default="small")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    cfg = yaml.safe_load((ROOT / "config" / "models.yaml").read_text(encoding="utf-8"))["local_model"]
    spec = cfg["choices"][args.choice]
    repo = spec["repo"]
    with httpx.Client(timeout=httpx.Timeout(30, read=300), follow_redirects=True) as http:
        info = http.get(f"https://huggingface.co/api/models/{repo}", params={"blobs": "true"})
        info.raise_for_status()
        siblings = [s for s in info.json().get("siblings", []) if isinstance(s, dict)]
        names = [str(s.get("rfilename", "")) for s in siblings]
        name = pick_file(names, spec)
        if name is None:
            print(f"no usable .gguf file in {repo}: {names}", file=sys.stderr)
            return 1
        sibling = next(s for s in siblings if s.get("rfilename") == name)
        lfs = sibling.get("lfs") or {}
        size, sha = int(lfs.get("size") or 0), str(lfs.get("sha256", ""))
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        target = out / name
        digest = hashlib.sha256()
        done = 0
        with http.stream("GET", f"https://huggingface.co/{repo}/resolve/main/{name}") as response:
            response.raise_for_status()
            with target.open("wb") as handle:
                for chunk in response.iter_bytes(1 << 20):
                    handle.write(chunk)
                    digest.update(chunk)
                    done += len(chunk)
    if (size and done != size) or (sha and digest.hexdigest() != sha):
        target.unlink(missing_ok=True)
        print(f"model download damaged ({done} of {size} bytes)", file=sys.stderr)
        return 1
    print(f"model ok: {target} ({done / 1e6:.0f} MB, sha256 {digest.hexdigest()[:16]}…)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
