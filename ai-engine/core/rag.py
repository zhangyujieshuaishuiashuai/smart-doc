from sentence_transformers import SentenceTransformer
import faiss
import numpy as np

class RAGEngine:
    def __init__(self):
        print(">>> [RAG] 加载 Embedding 模型 (text2vec-base-chinese)...")
        self.embed_model = SentenceTransformer('shibing624/text2vec-base-chinese')
        self.dimension = 768
        self.index = faiss.IndexFlatL2(self.dimension)
        self.doc_store = {} 
        self.counter = 0

    def add_document(self, text, source_filename):
        """
        优化后的切片策略：针对 Markdown 表格优化
        """
        print(f">>> [RAG] 开始切片并向量化: {source_filename}")
        
        # [策略调整]：
        # 对于表格类文档，切片不能太小。Markdown 表格一行就很长。
        chunk_size = 800  # 增大，容纳更多表格行
        overlap = 150     # 重叠，防止截断上下文
        
        # 简单的滑动窗口切片（按行处理，防止切断Markdown行）
        lines = text.split('\n')
        chunks = []
        current_chunk = []
        current_length = 0
        
        for line in lines:
            line_len = len(line)
            # 如果单行超长（极少情况），强制切断
            if line_len > chunk_size:
                chunks.append(line[:chunk_size])
                continue

            if current_length + line_len > chunk_size:
                # 当前块满了，保存
                full_chunk_text = "\n".join(current_chunk)
                chunks.append(full_chunk_text)
                
                # 开启新块，保留一部分重叠（比如最后 5 行）
                # 这样表头或者上下文能延续到下一块
                keep_lines = current_chunk[-5:] if len(current_chunk) > 5 else []
                current_chunk = keep_lines[:] # 浅拷贝
                current_length = sum(len(l) for l in keep_lines)
            
            current_chunk.append(line)
            current_length += line_len
            
        if current_chunk:
            chunks.append("\n".join(current_chunk))

        if not chunks: 
            return 0

        print(f">>> [RAG] 生成了 {len(chunks)} 个知识切片，开始 Embedding...")

        # 批量计算向量
        vectors = self.embed_model.encode(chunks)
        
        # 存入 FAISS
        self.index.add(np.array(vectors).astype('float32'))
        
        # 存元数据
        added_count = 0
        for i, chunk in enumerate(chunks):
            self.doc_store[self.counter] = {
                "text": chunk,
                "source": source_filename,
                "chunk_id": i
            }
            self.counter += 1
            added_count += 1
            
        return added_count

    def search(self, query, top_k=5): # 增加检索数量，提高召回率
        if self.index.ntotal == 0:
            return []
            
        q_vec = self.embed_model.encode([query])
        D, I = self.index.search(np.array(q_vec).astype('float32'), top_k)
        
        results = []
        for idx, doc_id in enumerate(I[0]):
            if doc_id == -1: continue
            meta = self.doc_store.get(doc_id, {})
            
            # 过滤掉太短的无意义片段
            if len(meta.get("text", "")) < 10:
                continue
                
            results.append({
                "score": float(D[0][idx]),
                "text": meta.get("text", ""),
                "source": meta.get("source", "")
            })
        return results