from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import shutil
import os
import uvicorn
# 确保导入路径正确
from core.parser import DocParser
from core.rag import RAGEngine

app = FastAPI(title="Smart Doc AI Engine")

# 允许跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 初始化模型
print("正在启动 AI 引擎...")
parser = DocParser()
rag = RAGEngine()

os.makedirs("temp_uploads", exist_ok=True)

class SearchRequest(BaseModel):
    query: str

@app.post("/api/upload")
async def upload_and_process(file: UploadFile = File(...)):
    print(f"收到文件上传请求: {file.filename}")
    file_path = f"temp_uploads/{file.filename}"
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    if file.filename.lower().endswith(".pdf"):
        full_text = parser.parse_pdf(file_path)
        if not full_text:
            return {"status": "error", "message": "解析结果为空"}
            
        chunks = rag.add_document(full_text, file.filename)
        return {
            "status": "success", 
            "filename": file.filename, 
            "chunks_added": chunks,
            "preview": full_text[:100]
        }
    return {"error": "仅支持 PDF"}

@app.post("/api/search")
async def search(req: SearchRequest):
    results = rag.search(req.query)
    return {"query": req.query, "context": "", "sources": results}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)