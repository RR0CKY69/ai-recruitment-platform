import secrets


def generate_workspace_slug(name: str) -> str:
    """Create a URL-safe workspace slug from its display name."""
    base = "".join(
        ch.lower() if ch.isalnum() else "-"
        for ch in name.strip()
    )
    base = "-".join(
        part for part in base.split("-") if part
    )[:60] or "workspace"

    return f"{base}-{secrets.token_urlsafe(4)}"
