from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import shutil
import os
import uvicorn
from core.parser import DocParser
from core.rag import RAGEngine

app = FastAPI(title="Smart Doc AI Engine")

# 允许跨域（这很重要，否则前端连不上）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

parser = DocParser()
rag = RAGEngine()

os.makedirs("temp_uploads", exist_ok=True)

class SearchRequest(BaseModel):
    query: str

class VectorAddRequest(BaseModel):
    text: str
    source: str
    extra_chunks: list[dict] | None = None

class VectorSearchRequest(BaseModel):
    query: str
    top_k: int | None = 5
    file_filter: str | None = None

@app.post("/api/upload")
async def upload_and_process(file: UploadFile = File(...)):
    file_path = f"temp_uploads/{file.filename}"
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    # 简单的 MVP 逻辑
    if file.filename.lower().endswith(".pdf"):
        full_text = parser.parse_pdf(file_path)
        chunks = rag.add_document(full_text, file.filename)
        return {"status": "success", "filename": file.filename, "chunks_added": chunks}
    return {"error": "仅支持 PDF"}

@app.post("/api/search")
async def search(req: SearchRequest):
    results = rag.search(req.query)
    return {"query": req.query, "context": "", "sources": results}

@app.post("/ocr/image")
async def ocr_image(file: UploadFile = File(...)):
    file_path = f"temp_uploads/{file.filename}"
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    if file.filename.lower().endswith(".pdf"):
        parsed = parser.parse_pdf(file_path)
        return {
            "text": parsed["text"],
            "pages": parsed["pages"],
            "tables": parsed["tables"]
        }

    text = parser.ocr_image(file_path)
    return {"text": text, "pages": []}

@app.post("/extract/pdf-table")
async def extract_pdf_table(file: UploadFile = File(...)):
    file_path = f"temp_uploads/{file.filename}"
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    tables = parser.extract_tables(file_path)
    return {"tables": tables}

@app.post("/vector/add")
async def vector_add(req: VectorAddRequest):
    chunks_added = rag.add_document(req.text, req.source, req.extra_chunks)
    return {"status": "success", "chunks_added": chunks_added}

@app.post("/vector/search")
async def vector_search(req: VectorSearchRequest):
    results = rag.search(req.query, req.top_k or 5, req.file_filter)
    return {"query": req.query, "context": "", "sources": results}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
