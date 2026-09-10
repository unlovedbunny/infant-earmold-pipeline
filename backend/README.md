# AuriMold API - Backend

## Instalação

1. Crie um ambiente virtual na pasta do backend:
   ```bash
   python -m venv venv
   ```
2. Ative o ambiente virtual:
   - Windows: `venv\Scripts\activate`
   - Linux/Mac: `source venv/bin/activate`
3. Instale as dependências:
   ```bash
   pip install -r requirements.txt
   ```

## Execução

Inicie o servidor de desenvolvimento a partir do diretório `backend`:
```bash
uvicorn app.main:app --reload
```
A API estará disponível em `http://localhost:8000`
A documentação (Swagger UI) estará em `http://localhost:8000/docs`
