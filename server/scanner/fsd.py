"""
Feature-Sliced Design (FSD) detection, classification, display names, and violation detection.
"""

import os
from pathlib import Path
from typing import Optional

# ───────────────────────── FSD Constants ─────────────────────────

# FSD canonical layer names (top → bottom, highest index = lowest layer)
FSD_LAYERS = ("app", "processes", "pages", "widgets", "features", "entities", "shared")

# FSD layer hierarchy index — lower number = higher layer (more authority)
FSD_LAYER_HIERARCHY: dict[str, int] = {
    "app": 0,
    "processes": 1,
    "pages": 2,
    "widgets": 3,
    "features": 4,
    "entities": 5,
    "shared": 6,
}

# Common FSD segments inside slices
FSD_SEGMENTS = {"ui", "api", "model", "lib", "config", "routes", "store", "styles", "i18n", "types", "consts"}


# ───────────────────────── FSD Detection ─────────────────────────

def detect_fsd(root: Path) -> bool:
    """
    Detect if a project follows Feature-Sliced Design architecture.
    Looks for at least 2 FSD-specific layer folders (entities, widgets, features)
    at the src/ or root level, with segment-like sub-structure.
    """
    src_root = root / "src" if (root / "src").is_dir() else root

    strong_signals = 0
    weak_signals = 0

    for layer_name in FSD_LAYERS:
        layer_dir = src_root / layer_name
        if not layer_dir.is_dir():
            continue

        if layer_name in ("entities", "widgets"):
            strong_signals += 1
        elif layer_name in ("features", "shared"):
            has_fsd_structure = False
            try:
                for child in layer_dir.iterdir():
                    if child.is_dir() and not child.name.startswith("."):
                        child_dirs = {c.name for c in child.iterdir() if c.is_dir()}
                        if child_dirs & FSD_SEGMENTS:
                            has_fsd_structure = True
                            break
            except OSError:
                pass
            if has_fsd_structure:
                weak_signals += 1
        elif layer_name == "app":
            try:
                child_dirs = {c.name for c in layer_dir.iterdir() if c.is_dir()}
                if child_dirs & {"routes", "styles", "store", "providers", "entrypoint"}:
                    weak_signals += 1
            except OSError:
                pass

    return strong_signals >= 1 or (weak_signals >= 2 and strong_signals >= 0)


# ───────────────────────── FSD Layer Classification ─────────────────────────

def classify_fsd_layer(p: str, rel_path: str, file_data: dict) -> str:
    """Classify a file into an FSD layer based on its path within src/."""
    normalized = p
    if normalized.startswith("src/"):
        normalized = normalized[4:]

    for fsd_layer in FSD_LAYERS:
        if normalized == fsd_layer or normalized.startswith(fsd_layer + "/"):
            return f"fsd_{fsd_layer}"

    return "fsd_app"


# ───────────────────────── FSD Display Name ─────────────────────────

def compute_fsd_display_name(parts: list[str], stem: str) -> str:
    """
    Compute display name for FSD files.
    Structure: src/<layer>/<slice>/<segment>/<file>
    - features/auth/ui/LoginForm.tsx → "auth/LoginForm"
    - entities/user/model/types.ts → "user/types"
    - shared/ui/Button.tsx → "ui/Button"
    - shared/api/client.ts → "api/client"
    - app/routes/index.ts → "routes/index"
    - pages/home/ui/HomePage.tsx → "home/HomePage"
    """
    if parts and parts[0] == "src":
        parts = parts[1:]

    if not parts:
        return stem

    fsd_layers_set = set(FSD_LAYERS)

    if parts[0] in fsd_layers_set:
        layer_name = parts[0]
        rest = parts[1:]

        if not rest:
            return stem

        # For app/ and shared/ — no slices, just segments
        if layer_name in ("app", "shared"):
            rest[-1] = stem
            if stem == "index" and len(rest) >= 2:
                rest = rest[:-1]
            elif len(rest) >= 2 and rest[-1].lower() == rest[-2].lower():
                rest = rest[:-1]
            return "/".join(rest)

        # For entities, features, widgets, pages, processes — slices then segments
        slice_name = rest[0]
        inner = rest[1:]

        if not inner:
            return slice_name

        inner[-1] = stem

        if stem == "index" and len(inner) >= 2:
            inner = inner[:-1]

        if len(inner) >= 2 and inner[0] in FSD_SEGMENTS:
            return f"{slice_name}/{'/'.join(inner[1:])}"

        if len(inner) == 1 and inner[0] == "index":
            return slice_name

        if len(inner) >= 2 and inner[-1].lower() == inner[-2].lower():
            inner = inner[:-1]
            if inner[0] in FSD_SEGMENTS and len(inner) >= 2:
                return f"{slice_name}/{'/'.join(inner[1:])}"
            return f"{slice_name}/{'/'.join(inner)}"

        return f"{slice_name}/{'/'.join(inner)}"

    if stem == "index" and len(parts) >= 2:
        return parts[-2]
    return stem


# ───────────────────────── FSD Violation Detection ─────────────────────────

def detect_fsd_violations(
    display_files: list[Path],
    file_layers: dict[Path, str],
    resolved_imports: dict[Path, list[Path]],
    node_id_map: dict[Path, str],
    resolve_through_barrels,
) -> list[dict]:
    """
    Detect FSD import rule violations.
    Rule: A module in a layer can only import from layers STRICTLY BELOW (higher index).
    Same-layer cross-slice imports are also violations (except within app/ and shared/).
    Imports within the same slice are always allowed.
    """
    violations: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def _get_fsd_slice(fp: Path) -> Optional[str]:
        """Extract the FSD slice name from a file path."""
        parts = list(fp.parts)
        for i, part in enumerate(parts):
            if part in set(FSD_LAYERS) and i + 1 < len(parts):
                if part in ("app", "shared"):
                    return None
                return parts[i + 1]
        return None

    for fp in display_files:
        src_layer = file_layers.get(fp, "")
        if not src_layer.startswith("fsd_"):
            continue
        src_layer_name = src_layer[4:]
        src_hierarchy = FSD_LAYER_HIERARCHY.get(src_layer_name)
        if src_hierarchy is None:
            continue
        src_id = node_id_map.get(fp)
        if not src_id:
            continue
        src_slice = _get_fsd_slice(fp)

        for dep in resolved_imports.get(fp, []):
            targets = resolve_through_barrels(dep)
            for actual_target in targets:
                tgt_layer = file_layers.get(actual_target, "")
                if not tgt_layer.startswith("fsd_"):
                    continue
                tgt_layer_name = tgt_layer[4:]
                tgt_hierarchy = FSD_LAYER_HIERARCHY.get(tgt_layer_name)
                if tgt_hierarchy is None:
                    continue
                tgt_id = node_id_map.get(actual_target)
                if not tgt_id or src_id == tgt_id:
                    continue

                if tgt_hierarchy < src_hierarchy:
                    key = (src_id, tgt_id)
                    if key not in seen:
                        seen.add(key)
                        violations.append({
                            "source": src_id,
                            "target": tgt_id,
                            "sourceLayer": src_layer_name,
                            "targetLayer": tgt_layer_name,
                            "type": "upward",
                        })

                elif tgt_hierarchy == src_hierarchy and src_layer_name not in ("app", "shared"):
                    tgt_slice = _get_fsd_slice(actual_target)
                    if src_slice != tgt_slice:
                        key = (src_id, tgt_id)
                        if key not in seen:
                            seen.add(key)
                            violations.append({
                                "source": src_id,
                                "target": tgt_id,
                                "sourceLayer": src_layer_name,
                                "targetLayer": tgt_layer_name,
                                "type": "cross-slice",
                            })

    return violations
