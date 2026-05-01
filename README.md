# Smart Doc Platform（方案 B）

目标：在 MVP 基础上支持 **扫描件 OCR**、**PDF 表格解析**、**中文向量检索**，并在前端提供「来源追溯」。

## 组件

- frontend-web：Vue3 + Element Plus（预览/表格/问答）
- backend-server：Spring Boot（文档管理 + 调度）
- ai-engine：FastAPI（OCR + 表格 + 向量库 + Chat）
- MySQL：存 documents / pages / tables

## 运行（docker-compose）

```bash
cd smart-doc-platform
#（可选）让 AI Engine 直接调用 LLM（OpenAI 兼容）
export OPENAI_API_KEY=你的key
# export OPENAI_BASE_URL=你的兼容地址（如有）
# export OPENAI_MODEL=gpt-4o-mini

docker compose up --build
```

- 前端：http://localhost:5173
- 后端：http://localhost:8080
- AI Engine：http://localhost:8000

## 关键 API

- 上传 PDF：`POST /api/docs/upload/pdf`
- 上传图片：`POST /api/docs/upload/image`
- 文档列表：`GET /api/docs`
- 文档详情：`GET /api/docs/{docId}`
- 页图：`GET /api/docs/{docId}/pages/{pageNo}/image`
- 表格 CSV：`GET /api/docs/{docId}/tables/{tableId}/csv`
- 问答：`POST /api/docs/chat`

> 如果没配置 LLM，问答接口会返回“未配置 LLM”提示，并把检索到的引用片段返回给前端。
