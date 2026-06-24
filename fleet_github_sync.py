#!/usr/bin/env python3
"""
fleet_github_sync.py
────────────────────
Sube los 3 archivos .txt del Fleet Calendar al repositorio de GitHub.
Los archivos deben existir previamente en el repo (hace UPDATE, no CREATE).

Uso:
    python fleet_github_sync.py

Dependencias (solo stdlib + requests):
    pip install requests
"""

import os
import sys
import base64
import requests
from pathlib import Path
from datetime import datetime

# ══════════════════════════════════════════════════════════════════════════════
#  CONFIGURACIÓN — editá estos valores antes de correr el script
# ══════════════════════════════════════════════════════════════════════════════

# Token de GitHub (Settings → Developer settings → Personal access tokens → Fine-grained)
# Permisos necesarios: Contents → Read and write
GITHUB_TOKEN = "ghp_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"

# Repositorio: "usuario/nombre-repo"
GITHUB_REPO  = "tu-usuario/tu-repo"

# Rama donde están los archivos
GITHUB_BRANCH = "main"

# Carpeta DENTRO del repo donde viven los .txt (vacío = raíz del repo)
# Ejemplo: "datos" → los archivos estarán en /datos/Pque.txt
REPO_FOLDER = ""

# Carpeta LOCAL donde están los 3 archivos .txt
# Podés usar ruta absoluta: r"C:\Users\vos\flota" o "/home/vos/flota"
# O ruta relativa al script: "." (misma carpeta)
LOCAL_FOLDER = "."

# Mapeo: nombre local → nombre en el repo (si son distintos, cambialos acá)
FILES = {
    "Pque.txt":          "Pque.txt",
    "scraped_data.txt":  "scraped_data.txt",
    "TelemGts_data.txt": "TelemGts_data.txt",
}

# ══════════════════════════════════════════════════════════════════════════════


def gh_api(method: str, path: str, token: str, **kwargs) -> requests.Response:
    """Wrapper para la GitHub REST API."""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept":        "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    return requests.request(method, url, headers=headers, **kwargs)


def get_file_sha(repo_path: str, token: str) -> str | None:
    """Obtiene el SHA del archivo en el repo (necesario para actualizarlo)."""
    r = gh_api("GET", f"contents/{repo_path}", token,
                params={"ref": GITHUB_BRANCH})
    if r.status_code == 200:
        return r.json().get("sha")
    elif r.status_code == 404:
        return None  # archivo no existe aún
    else:
        r.raise_for_status()


def upload_file(local_path: Path, repo_path: str, token: str) -> dict:
    """
    Sube un archivo al repo.
    Si ya existe → lo actualiza (PUT con sha).
    Si no existe → lo crea (PUT sin sha).
    """
    # Leer y codificar en base64
    content_bytes = local_path.read_bytes()
    content_b64   = base64.b64encode(content_bytes).decode()

    # Obtener SHA actual (para update)
    sha = get_file_sha(repo_path, token)

    # Mensaje del commit
    action    = "update" if sha else "create"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    message   = f"fleet-sync: {action} {local_path.name} — {timestamp}"

    # Body del PUT
    body = {
        "message": message,
        "content": content_b64,
        "branch":  GITHUB_BRANCH,
    }
    if sha:
        body["sha"] = sha

    r = gh_api("PUT", f"contents/{repo_path}", token, json=body)
    r.raise_for_status()
    return r.json()


def validate_config() -> list[str]:
    """Valida la configuración antes de hacer nada."""
    errors = []
    if GITHUB_TOKEN.startswith("ghp_XXX"):
        errors.append("GITHUB_TOKEN no fue configurado.")
    if "/" not in GITHUB_REPO or "tu-usuario" in GITHUB_REPO:
        errors.append("GITHUB_REPO no fue configurado (formato: usuario/repo).")
    return errors


def main():
    print("═" * 56)
    print("  Fleet Calendar — GitHub Sync")
    print(f"  {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print("═" * 56)

    # ── Validar config ──────────────────────────────────────────
    errors = validate_config()
    if errors:
        print("\n❌  Errores de configuración:")
        for e in errors:
            print(f"    • {e}")
        print("\n  Editá las variables al inicio del script y volvé a correr.")
        sys.exit(1)

    local_dir = Path(LOCAL_FOLDER).expanduser().resolve()
    if not local_dir.exists():
        print(f"\n❌  Carpeta local no encontrada: {local_dir}")
        sys.exit(1)

    print(f"\n  Repo:    {GITHUB_REPO}  [{GITHUB_BRANCH}]")
    print(f"  Local:   {local_dir}")
    print(f"  Carpeta repo: /{REPO_FOLDER or '(raíz)'}")
    print()

    # ── Verificar que los archivos locales existen ──────────────
    missing = []
    for local_name in FILES:
        if not (local_dir / local_name).exists():
            missing.append(local_name)
    if missing:
        print("❌  Archivos no encontrados en la carpeta local:")
        for m in missing:
            print(f"    • {m}")
        sys.exit(1)

    # ── Subir archivos ──────────────────────────────────────────
    results = []
    for local_name, repo_name in FILES.items():
        local_path = local_dir / local_name
        repo_path  = f"{REPO_FOLDER}/{repo_name}".lstrip("/")
        size_kb    = local_path.stat().st_size / 1024

        print(f"  ⟳  {local_name}  ({size_kb:.1f} KB) → {repo_path}")

        try:
            result = upload_file(local_path, repo_path, GITHUB_TOKEN)
            commit_url = result.get("commit", {}).get("html_url", "")
            sha_short  = result.get("commit", {}).get("sha", "")[:7]
            print(f"  ✅  OK — commit {sha_short}")
            if commit_url:
                print(f"       {commit_url}")
            results.append(("ok", local_name))
        except requests.HTTPError as e:
            status = e.response.status_code
            msg    = e.response.json().get("message", str(e))
            print(f"  ❌  Error HTTP {status}: {msg}")
            if status == 401:
                print("       → Token inválido o sin permisos.")
            elif status == 404:
                print("       → Repo no encontrado o sin acceso.")
            elif status == 409:
                print("       → Conflicto de SHA. El archivo cambió en el repo.")
                print("         Volvé a correr el script (obtiene el SHA actualizado).")
            results.append(("err", local_name))
        except Exception as e:
            print(f"  ❌  Error inesperado: {e}")
            results.append(("err", local_name))
        print()

    # ── Resumen ─────────────────────────────────────────────────
    ok  = sum(1 for s, _ in results if s == "ok")
    err = sum(1 for s, _ in results if s == "err")
    print("─" * 56)
    if err == 0:
        print(f"  ✅  {ok}/3 archivos sincronizados correctamente.")
    else:
        print(f"  ⚠️   {ok}/3 OK · {err} con errores — revisá los mensajes arriba.")
    print("─" * 56)
    sys.exit(0 if err == 0 else 1)


if __name__ == "__main__":
    main()
