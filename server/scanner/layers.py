"""
Layer classification, display name computation, and route extraction.
"""

import os
from pathlib import Path
from typing import Optional

from .fsd import FSD_LAYERS, classify_fsd_layer, compute_fsd_display_name

# ───────────────────────── Layer Classification ─────────────────────────


def classify_layer(rel_path: str, framework: str, file_data: dict, is_fsd: bool = False) -> str:
    """
    Classify a file into a layer based on its path and the framework.
    Returns: 'page', 'feature', 'shared', 'api_service', 'api_route', 'layout', 'middleware'
    Or for FSD: 'fsd_app', 'fsd_processes', 'fsd_pages', 'fsd_widgets', 'fsd_features', 'fsd_entities', 'fsd_shared'
    """
    p = rel_path.lower().replace("\\", "/")
    name = os.path.basename(rel_path).lower()
    stem = os.path.splitext(name)[0]

    # ── Feature-Sliced Design ──
    if is_fsd:
        return classify_fsd_layer(p, rel_path, file_data)

    # ── Next.js App Router ──
    if framework == "nextjs":
        if "/app/" in p and "/api/" in p and stem in ("route", "route.ts", "route.js"):
            return "api_route"
        if stem == "route":
            return "api_route"
        if stem == "page":
            return "page"
        if stem == "layout" and "/app/" in p:
            return "layout"
        if stem in ("loading", "error", "not-found", "global-error", "template"):
            return "shared"
        if stem == "middleware":
            return "middleware"
        if "/pages/" in p and stem not in ("_app", "_document"):
            if "/api/" in p:
                return "api_route"
            return "page"
        if stem in ("_app", "_document"):
            return "layout"

    # ── TanStack Router ──
    elif framework == "tanstack-router":
        if "/routes/" in p:
            if stem == "__root" or stem == "__root.tsx":
                return "layout"
            if stem.startswith("_"):
                return "layout"
            return "page"

    # ── Remix ──
    elif framework == "remix":
        if "/routes/" in p:
            if stem.startswith("_"):
                return "layout"
            return "page"
        if "/app/root" in p:
            return "layout"

    # ── Gatsby ──
    elif framework == "gatsby":
        if "/pages/" in p:
            return "page"
        if "/templates/" in p:
            return "page"

    # ── Generic / Classic React ──
    if any(seg in p for seg in ["/pages/", "/views/", "/screens/"]):
        return "page"
    if any(seg in p for seg in ["/routes/"]):
        if stem in ("index", "__root"):
            return "layout"
        return "page"

    if any(seg in p for seg in [
        "/services/", "/api/", "/lib/api", "/utils/api",
        "/queries/", "/mutations/",
    ]):
        return "api_service"
    if "/hooks/" in p and stem.startswith("use"):
        if file_data.get("api_calls"):
            return "api_service"
        return "shared"

    if any(seg in p for seg in ["/features/", "/modules/", "/containers/", "/sections/", "/domains/"]):
        return "feature"

    if any(seg in p for seg in [
        "/components/", "/ui/", "/shared/", "/common/", "/elements/",
        "/atoms/", "/molecules/", "/organisms/",
        "/primitives/",
    ]):
        return "shared"

    if any(seg in p for seg in ["/store/", "/stores/", "/state/", "/redux/", "/zustand/", "/context/"]):
        return "shared"

    if any(seg in p for seg in ["/lib/", "/utils/", "/helpers/", "/config/"]):
        return "shared"

    return "shared"


LAYER_ORDER = {
    "page": 0,
    "layout": 0,
    "feature": 1,
    "shared": 2,
    "api_service": 3,
    "api_route": 3,
    "middleware": 2,
    # FSD layers (ordered top → bottom)
    "fsd_app": 0,
    "fsd_processes": 1,
    "fsd_pages": 2,
    "fsd_widgets": 3,
    "fsd_features": 4,
    "fsd_entities": 5,
    "fsd_shared": 6,
}

LAYER_LABELS = {
    "page": "Pages",
    "layout": "Layouts",
    "feature": "Features",
    "shared": "Shared / UI",
    "api_service": "API Services",
    "api_route": "API Routes",
    "middleware": "Middleware",
    # FSD layers
    "fsd_app": "App",
    "fsd_processes": "Processes",
    "fsd_pages": "Pages",
    "fsd_widgets": "Widgets",
    "fsd_features": "Features",
    "fsd_entities": "Entities",
    "fsd_shared": "Shared",
}


# ───────────────────────── Display Name ─────────────────────────

def compute_display_name(fp: Path, root: Path, framework: str, is_fsd: bool = False) -> str:
    """
    Compute a human-friendly display name for a file.
    - Button/index.tsx → "Button"
    - app/blog/[slug]/page.tsx → "/blog/[slug]"
    - routes/posts.$postId.tsx → "/posts/$postId"
    - FSD: features/auth/ui/LoginForm.tsx → "auth/LoginForm"
    """
    rel = fp.relative_to(root)
    parts = list(rel.parts)
    stem = fp.stem
    name = fp.name

    # ── FSD display names ──
    if is_fsd:
        return compute_fsd_display_name(parts, stem)

    # ── Next.js App Router ──
    if framework == "nextjs" and "app" in parts:
        app_idx = parts.index("app")
        route_parts = parts[app_idx + 1:]
        if stem in ("page", "layout", "loading", "error", "route", "not-found", "template"):
            route_parts = route_parts[:-1]
            route_parts = [p for p in route_parts if not (p.startswith("(") and p.endswith(")"))]
            route = "/" + "/".join(route_parts) if route_parts else "/"
            label = stem.capitalize()
            if stem == "page":
                return route
            return f"{route} ({label})"

        if "pages" in parts:
            pages_idx = parts.index("pages")
            route_parts = parts[pages_idx + 1:-1]
            base = fp.stem
            if base == "index":
                return "/" + "/".join(route_parts) if route_parts else "/"
            route_parts.append(base)
            return "/" + "/".join(route_parts)

    # ── Next.js Pages Router ──
    if framework == "nextjs" and "pages" in parts:
        pages_idx = parts.index("pages")
        route_parts = parts[pages_idx + 1:]
        route_parts[-1] = stem
        if stem.startswith("_"):
            return stem
        if stem == "index":
            route_parts = route_parts[:-1]
        return "/" + "/".join(route_parts) if route_parts else "/"

    # ── TanStack Router ──
    if framework == "tanstack-router" and "routes" in parts:
        routes_idx = parts.index("routes")
        route_parts = parts[routes_idx + 1:]
        route_parts[-1] = stem
        route_str = "/".join(route_parts)
        route_str = route_str.replace(".", "/")
        if route_str == "index" or route_str == "__root":
            return "/" if route_str == "index" else "__root"
        return "/" + route_str

    # ── Remix ──
    if framework == "remix" and "routes" in parts:
        routes_idx = parts.index("routes")
        route_parts = parts[routes_idx + 1:]
        route_parts[-1] = stem
        route_str = "/".join(route_parts)
        route_str = route_str.replace(".", "/")
        if route_str.startswith("_"):
            return route_str
        return "/" + route_str

    # ── Folder-based component: Button/index.tsx → "Button" ──
    if stem == "index" and len(parts) >= 2:
        return parts[-2]

    # ── Folder-based: PostFeed/PostFeed.tsx → "PostFeed" ──
    if len(parts) >= 2 and stem.lower() == parts[-2].lower():
        return stem

    return stem


def extract_file_route(fp: Path, root: Path, framework: str) -> Optional[str]:
    """Extract the URL route from file path for file-based routing frameworks."""
    rel = fp.relative_to(root)
    parts = list(rel.parts)
    stem = fp.stem

    if framework == "nextjs":
        if "app" in parts:
            app_idx = parts.index("app")
            route_parts = parts[app_idx + 1:]
            if stem in ("page", "route"):
                route_parts = route_parts[:-1]
                route_parts = [p for p in route_parts if not (p.startswith("(") and p.endswith(")"))]
                return "/" + "/".join(route_parts) if route_parts else "/"
        if "pages" in parts:
            pages_idx = parts.index("pages")
            route_parts = parts[pages_idx + 1:]
            route_parts[-1] = stem
            if stem == "index":
                route_parts = route_parts[:-1]
            if stem.startswith("_"):
                return None
            return "/" + "/".join(route_parts) if route_parts else "/"

    if framework == "tanstack-router" and "routes" in parts:
        routes_idx = parts.index("routes")
        route_parts = parts[routes_idx + 1:]
        route_parts[-1] = stem
        route_str = "/".join(route_parts).replace(".", "/")
        if route_str in ("index", "__root"):
            return "/" if route_str == "index" else None
        return "/" + route_str

    if framework == "remix" and "routes" in parts:
        routes_idx = parts.index("routes")
        route_parts = parts[routes_idx + 1:]
        route_parts[-1] = stem
        route_str = "/".join(route_parts).replace(".", "/")
        if route_str.startswith("_"):
            return None
        return "/" + route_str

    return None
