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

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)