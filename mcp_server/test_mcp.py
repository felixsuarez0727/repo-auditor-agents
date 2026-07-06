import asyncio
from mcp_server.github_mcp import get_repo_metadata, list_repo_files, read_file_content

async def main():
    owner = "octocat"
    repo = "Hello-World"
    
    print("--- 1. Probando get_repo_metadata ---")
    try:
        metadata = await get_repo_metadata(owner, repo)
        print("Metadata obtenida:")
        print(metadata)
    except Exception as e:
        print(f"Error en get_repo_metadata: {e}")
        
    print("\n--- 2. Probando list_repo_files ---")
    try:
        files = await list_repo_files(owner, repo)
        print("Archivos en la raíz:")
        for f in files:
            print(f"- {f['name']} ({f['type']})")
    except Exception as e:
        print(f"Error en list_repo_files: {e}")
        
    print("\n--- 3. Probando read_file_content ---")
    try:
        # octocat/Hello-World has a README file at the root
        content = await read_file_content(owner, repo, "README")
        print("Contenido del archivo README:")
        print(content.strip())
    except Exception as e:
        print(f"Error en read_file_content: {e}")

if __name__ == "__main__":
    asyncio.run(main())
