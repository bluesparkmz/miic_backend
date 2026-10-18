import uvicorn

if __name__ == "__main__":
    print("Iniciando backend MIIC 2026 em http://127.0.0.1:8000...")
    print("Documentação Swagger UI disponível em: http://127.0.0.1:8000/docs")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
