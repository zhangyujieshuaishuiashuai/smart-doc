import axios from "axios";

export const backendBaseURL =
  import.meta.env.VITE_BACKEND_BASE_URL || "http://localhost:8080";

export const agentBaseURL =
  import.meta.env.VITE_AGENT_BASE_URL || "http://127.0.0.1:8001";

const api = axios.create({
  baseURL: backendBaseURL,
  timeout: 600_000,
});

/**从文档中提取出的表格数据 与后端对齐；部分字段可能为 snake_case */
export type ExtractedTable = {
  id: string | number;
  page?: number;
  pageNo?: number;
  title?: string;
  markdown?: string;
  tableMarkdown?: string | null;
  html?: string;
  rows?: string[][];
  tableJson?: string | null;
};

export type Document = {
  id: number;
  filename: string;
  fileName?: string;
  status: number;
  vectorDocId?: number | null;
  ocrText?: string;
  tableJson?: string;
  createTime?: string;
  rawOcrText?: string;
  displayText?: string;
  cleanTextForRag?: string;
  raw_ocr_text?: string;
  display_text?: string;
  clean_text_for_rag?: string;
  tables?: ExtractedTable[];
  /** 结构化表格提取状态（空表时的说明依据） */
  tableExtractStatus?: string;
};

export interface DocumentPage {
  page: number;
  imagePath?: string;
  imageUrl?: string;
  text?: string;
  displayText?: string;
  cleanTextForRag?: string;
  rawOcrText?: string;
  // 为了兼容现有代码，添加 ocrLinesJson 字段
  ocrLinesJson?: string | null;
}

export interface DocumentDetail extends Document {
  fileName: string;
  fileType?: string;
  cleanMode?: string;
  pages?: DocumentPage[];
  tables?: ExtractedTable[];
}

/** 
 * @deprecated Use DocumentDetail instead
 */
export type DocumentDetailLegacy = Document & {
  pages?: DocumentPage[];
  tables?: ExtractedTable[];
};

export async function listDocs(): Promise<Document[]> {
  const res = await api.get<Document[]>("/api/docs");
  return res.data;
}

export async function getDocDetail(docId: number): Promise<DocumentDetail> {
  const res = await api.get<DocumentDetail>(`/api/docs/${docId}`);
  return res.data;
}

export async function uploadPdf(file: File, cleanMode: string): Promise<Document> {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("clean_mode", cleanMode);
  const res = await api.post<Document>("/api/docs/upload/pdf", fd);
  return res.data;
}

export async function uploadImage(file: File, cleanMode: string): Promise<Document> {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("clean_mode", cleanMode);
  const res = await api.post<Document>("/api/docs/upload/image", fd);
  return res.data;
}

export async function reparseDoc(docId: number, cleanMode: string): Promise<void> {
  await api.post(`/api/docs/${docId}/reparse`, {
    cleanMode,
    clean_mode: cleanMode,
  });
}

export async function chat(query: string, currentFile?: string): Promise<{ answer: string; sources: any[] }> {
  const res = await api.post("/api/docs/chat", { query, currentFile });
  return res.data;
}

/** 页面预览图由 Spring Boot（storage/pages）提供，与 DocQueryController 一致 */
export function pageImageUrl(docId: number, pageNo: number): string {
  return `${backendBaseURL}/api/docs/${docId}/pages/${pageNo}/image`;
}

export function tableCsvUrl(docId: number, tableId: string | number): string {
  return `${backendBaseURL}/api/docs/${docId}/tables/${encodeURIComponent(String(tableId))}/csv`;
}

export async function searchDocuments(params: { keyword: string; isolate?: boolean; docId?: number }) {
  const res = await api.post("/api/docs/search", params);
  return res.data;
}

export interface ChatRequest {
  question: string;
  docId?: number;
  isolate: boolean;
  docIds?: number[];
}

export interface ChatResponse {
  answer: string;
  contexts?: any[];
}

export async function chatNew(req: ChatRequest): Promise<ChatResponse> {
  const res = await api.post<ChatResponse>("/api/docs/chat", req);
  return res.data;
}
