import os
import httpx
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# Initialize FastMCP server
mcp = FastMCP("GitHub MCP Server")

GITHUB_API_URL = "https://api.github.com"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

def get_headers():
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "GitHub-MCP-Server-Python",
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers

@mcp.tool()
async def get_repo_metadata(owner: str, repo: str) -> dict:
    """
    Obtiene los metadatos básicos de un repositorio de GitHub (nombre, descripción, lenguaje principal).
    
    Args:
        owner: El propietario del repositorio (usuario u organización).
        repo: El nombre del repositorio.
    """
    url = f"{GITHUB_API_URL}/repos/{owner}/{repo}"
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=get_headers())
        if response.status_code != 200:
            return {"error": f"Error al obtener metadata ({response.status_code}): {response.text}"}
        
        data = response.json()
        return {
            "name": data.get("name"),
            "description": data.get("description"),
            "language": data.get("language"),
            "stars": data.get("stargazers_count"),
            "forks": data.get("forks_count"),
            "default_branch": data.get("default_branch")
        }

@mcp.tool()
async def list_repo_files(owner: str, repo: str, path: str = "") -> list:
    """
    Lista los archivos y directorios de un repositorio en la ruta especificada.
    
    Args:
        owner: El propietario del repositorio.
        repo: El nombre del repositorio.
        path: La ruta dentro del repositorio (dejar vacío para la raíz).
    """
    url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/contents/{path}"
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=get_headers())
        if response.status_code != 200:
            raise Exception(f"Error al listar archivos ({response.status_code}): {response.text}")
        
        data = response.json()
        if not isinstance(data, list):
            # If the path is a file instead of a directory
            return [{"name": data.get("name"), "path": data.get("path"), "type": "file"}]
        
        result = []
        for item in data:
            result.append({
                "name": item.get("name"),
                "path": item.get("path"),
                "type": item.get("type"),
                "size": item.get("size")
            })
        return result

@mcp.tool()
async def read_file_content(owner: str, repo: str, path: str) -> str:
    """
    Lee y devuelve el contenido de un archivo específico de un repositorio de GitHub.
    
    Args:
        owner: El propietario del repositorio.
        repo: El nombre del repositorio.
        path: La ruta al archivo.
    """
    url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/contents/{path}"
    headers = get_headers()
    # Accept raw format to get file contents as raw text directly
    headers["Accept"] = "application/vnd.github.raw"
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        if response.status_code != 200:
            raise Exception(f"Error al leer archivo ({response.status_code}): {response.text}")
        
        return response.text

if __name__ == "__main__":
    mcp.run()
