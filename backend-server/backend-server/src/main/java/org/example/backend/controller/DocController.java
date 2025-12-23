package org.example.backend.controller;

import org.example.backend.client.AiEngineClient;
import org.example.backend.entity.Document;
import org.example.backend.entity.DocumentPage;
import org.example.backend.entity.DocumentTable;
import org.example.backend.repository.DocumentPageRepository;
import org.example.backend.repository.DocumentRepository;
import org.example.backend.repository.DocumentTableRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/docs")
@RequiredArgsConstructor
@Slf4j
@CrossOrigin(origins = "*")
public class DocController {

    private final AiEngineClient aiClient;
    private final DocumentRepository docRepo;
    private final DocumentPageRepository pageRepo;
    private final DocumentTableRepository tableRepo;
    private final ObjectMapper objectMapper = new ObjectMapper();

    // 通用处理逻辑：上传 -> 识别文字 -> 入库向量 -> (如果是PDF)解析表格
    private Document processFile(MultipartFile file, boolean isPdf) {
        log.info(">>> 开始处理文件: {}", file.getOriginalFilename());

        Document doc = new Document();
        doc.setFilename(file.getOriginalFilename());
        doc.setStatus(0);
        doc = docRepo.save(doc);

        try {
            // 1. 无论图片还是 PDF，都先调用 OCR 提取全文 (Python端已升级支持PDF)
            Map<String, Object> ocrResult = aiClient.ocrImage(file);
            log.info("OCR/文本提取结果: {}", ocrResult);

            String text = "";
            if (ocrResult.containsKey("text")) {
                text = ocrResult.get("text").toString();
                doc.setOcrText(text);
            }

            List<DocumentPage> pagesToSave = new ArrayList<>();
            if (ocrResult.containsKey("pages")) {
                List<Map<String, Object>> pages = objectMapper.convertValue(
                    ocrResult.get("pages"),
                    objectMapper.getTypeFactory().constructCollectionType(List.class, Map.class)
                );
                for (Map<String, Object> page : pages) {
                    DocumentPage docPage = new DocumentPage();
                    docPage.setDocument(doc);
                    docPage.setPageNo(parseInteger(page.get("page_no")));
                    docPage.setOcrText(valueToString(page.get("ocr_text")));
                    docPage.setImagePath(valueToString(page.get("image_path")));
                    pagesToSave.add(docPage);
                }
            }

            Map<String, Object> tableResult = null;
            if (isPdf && ocrResult.containsKey("tables")) {
                tableResult = Map.of("tables", ocrResult.get("tables"));
            }

            // 3. 如果是 PDF，额外尝试解析表格
            if (isPdf) {
                try {
                    if (tableResult == null) {
                        tableResult = aiClient.extractTable(file);
                    }
                    doc.setTableJson(objectMapper.writeValueAsString(tableResult));
                } catch (Exception e) {
                    log.warn("表格解析非致命错误: {}", e.getMessage());
                }
            }

            List<Map<String, Object>> tableEntries = new ArrayList<>();
            if (tableResult != null && tableResult.get("tables") != null) {
                tableEntries = objectMapper.convertValue(
                    tableResult.get("tables"),
                    objectMapper.getTypeFactory().constructCollectionType(List.class, Map.class)
                );
            }

            if (!pagesToSave.isEmpty()) {
                pageRepo.saveAll(pagesToSave);
            }

            if (!tableEntries.isEmpty()) {
                List<DocumentTable> tablesToSave = new ArrayList<>();
                for (Map<String, Object> table : tableEntries) {
                    DocumentTable docTable = new DocumentTable();
                    docTable.setDocument(doc);
                    docTable.setPageNo(parseInteger(table.get("page_no")));
                    docTable.setTableMarkdown(valueToString(table.get("table_markdown")));
                    docTable.setTableJson(jsonString(table.get("table_json")));
                    tablesToSave.add(docTable);
                }
                tableRepo.saveAll(tablesToSave);
            }

            if (!text.isEmpty() || !tableEntries.isEmpty()) {
                // 2. 【关键】将提取的文本存入向量库 (AI 才能记住！)
                Map<String, Object> vectorReq = new HashMap<>();
                vectorReq.put("text", text);
                vectorReq.put("source", file.getOriginalFilename());

                if (!tableEntries.isEmpty()) {
                    List<Map<String, Object>> extraChunks = new ArrayList<>();
                    for (Map<String, Object> table : tableEntries) {
                        Map<String, Object> chunk = new HashMap<>();
                        chunk.put("text", valueToString(table.get("table_markdown")));
                        chunk.put("chunk_type", "table");
                        chunk.put("page_no", parseInteger(table.get("page_no")));
                        chunk.put("table_id", parseInteger(table.get("table_id")));
                        extraChunks.add(chunk);
                    }
                    vectorReq.put("extra_chunks", extraChunks);
                }

                Map<String, Object> vectorRes = aiClient.addVector(vectorReq);
                log.info("向量入库结果: {}", vectorRes);
            }

            doc.setStatus(1);

        } catch (Exception e) {
            log.error("文件处理失败", e);
            doc.setStatus(2);
        }

        return docRepo.save(doc);
    }

    private Integer parseInteger(Object value) {
        if (value == null) {
            return null;
        }
        if (value instanceof Number number) {
            return number.intValue();
        }
        try {
            return Integer.parseInt(value.toString());
        } catch (NumberFormatException e) {
            return null;
        }
    }

    private String valueToString(Object value) {
        return value == null ? null : value.toString();
    }

    private String jsonString(Object value) {
        if (value == null) {
            return null;
        }
        try {
            return objectMapper.writeValueAsString(value);
        } catch (Exception e) {
            log.warn("表格 JSON 序列化失败: {}", e.getMessage());
            return value.toString();
        }
    }

    @PostMapping("/upload/image")
    public Document uploadImage(@RequestParam("file") MultipartFile file) {
        return processFile(file, false);
    }

    @PostMapping("/upload/pdf")
    public Document uploadPdf(@RequestParam("file") MultipartFile file) {
        return processFile(file, true);
    }

    @PostMapping("/chat")
    public Map<String, Object> chat(@RequestBody Map<String, String> request) {
        String question = request.get("query");
        String currentFile = request.get("currentFile");

        log.info("收到提问: {} (限定文件: {})", question, currentFile);

        Map<String, Object> searchReq = new HashMap<>();
        searchReq.put("query", question);
        searchReq.put("top_k", 20);

        if (currentFile != null && !currentFile.isEmpty()) {
            searchReq.put("file_filter", currentFile);
        }

        return aiClient.searchVector(searchReq);
    }
}
