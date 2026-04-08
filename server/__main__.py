#!/usr/bin/env python3
"""
CLI entry point for the scanner.
Usage: python -m server.scanner <repo_path> [output_path]
"""

import json
import os
import sys

from .scanner import scan_repository


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m server <repo_path> [output_path]")
        sys.exit(1)

    repo_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else "structure.json"

    if not os.path.isdir(repo_path):
        print(f"Error: '{repo_path}' is not a directory")
        sys.exit(1)

    print(f"Scanning repository: {repo_path}")
    structure = scan_repository(repo_path)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(structure, f, indent=2)

    meta = structure["metadata"]
    print(f"Framework: {meta['framework']}")
    if meta.get("isFsd"):
        print("Architecture: Feature-Sliced Design (FSD)")
    print(f"Done! Analyzed {meta['analyzedFiles']}/{meta['totalFiles']} files "
          f"({meta['treeShakedFiles']} tree-shaked, {meta['barrelFiles']} barrels)")
    print(f"Nodes: {len(structure['nodes'])}, Edges: {meta['totalEdges']}, "
          f"API Endpoints: {meta['apiEndpoints']}")
    if structure.get("analytics", {}).get("fsdViolations"):
        violations = structure["analytics"]["fsdViolations"]
        print(f"FSD Import Violations: {len(violations)}")
    print(f"Output: {output_path}")


if __name__ == "__main__":
    main()
