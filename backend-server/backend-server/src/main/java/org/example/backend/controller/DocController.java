package org.example.backend.controller;

import org.example.backend.client.AiEngineClient;
import org.example.backend.entity.Document;
import org.example.backend.repository.DocumentRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.util.HashMap;
import java.util.Map;

@RestController
@RequestMapping("/api/docs")
@RequiredArgsConstructor
@Slf4j
@CrossOrigin(origins = "*")
public class DocController {

    private final AiEngineClient aiClient;
    private final DocumentRepository docRepo;
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

            if (ocrResult.containsKey("text")) {
                String text = ocrResult.get("text").toString();
                doc.setOcrText(text);

                // 2. 【关键】将提取的文本存入向量库 (AI 才能记住！)
                Map<String, Object> vectorReq = new HashMap<>();
                vectorReq.put("text", text);
                vectorReq.put("source", file.getOriginalFilename());

                Map<String, Object> vectorRes = aiClient.addVector(vectorReq);
                log.info("向量入库结果: {}", vectorRes);
            }

            // 3. 如果是 PDF，额外尝试解析表格
            if (isPdf) {
                try {
                    Map<String, Object> tableResult = aiClient.extractTable(file);
                    doc.setTableJson(objectMapper.writeValueAsString(tableResult));
                } catch (Exception e) {
                    log.warn("表格解析非致命错误: {}", e.getMessage());
                }
            }

            doc.setStatus(1);

        } catch (Exception e) {
            log.error("文件处理失败", e);
            doc.setStatus(2);
        }

        return docRepo.save(doc);
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