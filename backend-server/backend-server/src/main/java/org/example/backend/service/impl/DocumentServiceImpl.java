package org.example.backend.service.impl;

import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.example.backend.client.AiEngineClient;
import org.example.backend.client.AiEnginePdfClient;
import org.example.backend.entity.Document;
import org.example.backend.entity.DocumentPage;
import org.example.backend.entity.DocumentTable;
import org.example.backend.repository.DocumentPageRepository;
import org.example.backend.repository.DocumentRepository;
import org.example.backend.repository.DocumentTableRepository;
import org.example.backend.service.DocumentService;
import org.example.backend.util.InMemoryMultipartFile;
import org.example.backend.vo.ChatRequest;
import org.example.backend.vo.ChatResponse;
import org.example.backend.vo.DocumentVO;
import org.example.backend.vo.DocumentVoMapper;
import org.example.backend.vo.SearchHitVO;
import org.example.backend.vo.SearchRequest;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClientResponseException;
import feign.FeignException;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.*;

@Service
@RequiredArgsConstructor
@Slf4j
public class DocumentServiceImpl implements DocumentService {

    @Value("${storage.base-dir:./data}")
    private String storageBaseDir;

    private final AiEngineClient aiClient;
    private final AiEnginePdfClient aiEnginePdfClient;
    private final DocumentRepository docRepo;
    private final DocumentPageRepository pageRepo;
    private final DocumentTableRepository tableRepo;

    private final ObjectMapper objectMapper;

    @Override
    public DocumentVO uploadImage(MultipartFile file, String cleanMode) {
        return processUpload(file, false, cleanMode);
    }

    @Override
    public DocumentVO uploadPdf(MultipartFile file, String cleanMode) {
        return processUpload(file, true, cleanMode);
    }

    @Override
    @Transactional
    public DocumentVO reparse(Long id, String cleanMode) {
        Document doc = docRepo.findById(id)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "文档不存在"));
        String effectiveCleanMode = (cleanMode == null || cleanMode.isBlank())
                ? ((doc.getCleanMode() == null || doc.getCleanMode().isBlank()) ? "general" : doc.getCleanMode())
                : cleanMode.trim();
        log.info("reparse docId={}, cleanMode={}", id, effectiveCleanMode);

        Path uploadDir = Paths.get(storageBaseDir, "uploads", String.valueOf(id));
        Path savedPath = uploadDir.resolve(doc.getFilename());
        if (!Files.exists(savedPath)) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "原始文件不存在，无法重新解析");
        }

        try {
            byte[] bytes = Files.readAllBytes(savedPath);
            boolean isPdf = "pdf".equalsIgnoreCase(doc.getFileType())
                    || (doc.getFilename() != null && doc.getFilename().toLowerCase(Locale.ROOT).endsWith(".pdf"));

            Map<String, Object> parseResult;
            if (isPdf) {
                log.info("call agent /parse/pdf, filename={}, cleanMode={}", doc.getFilename(), effectiveCleanMode);
                parseResult = aiEnginePdfClient.parsePdf(bytes, doc.getFilename(), String.valueOf(id), effectiveCleanMode);
            } else {
                MultipartFile mf = new InMemoryMultipartFile(
                        "file",
                        doc.getFilename(),
                        guessImageContentType(doc.getFilename()),
                        bytes);
                log.info("call agent /parse/image, filename={}, cleanMode={}", doc.getFilename(), effectiveCleanMode);
                parseResult = aiClient.parseImage(mf, effectiveCleanMode, String.valueOf(id), "true");
            }

            doc.setCleanMode(effectiveCleanMode);

            fillDocumentFromParseResult(doc, parseResult);

            pageRepo.deleteAll(pageRepo.findByDocumentIdOrderByPageNoAsc(id));
            tableRepo.deleteAll(tableRepo.findByDocumentIdOrderByIdAsc(id));

            List<DocumentPage> pagesToSave = extractPages(parseResult, doc);
            if (!pagesToSave.isEmpty()) {
                pageRepo.saveAll(pagesToSave);
            }

            List<DocumentTable> tablesToSave = extractTables(parseResult, doc);
            if (!tablesToSave.isEmpty()) {
                tableRepo.saveAll(tablesToSave);
            }

            boolean indexed = ensureVectorIndexState(doc, parseResult);
            doc.setStatus(indexed ? 1 : 2);
            doc = docRepo.save(doc);
            log.info("reparse persisted docId={}, cleanMode={}, pages={}, tables={}, indexed={}",
                    doc.getId(), doc.getCleanMode(), pagesToSave.size(), tablesToSave.size(), indexed);
            return DocumentVoMapper.toVo(
                    doc,
                    pageRepo.findByDocumentIdOrderByPageNoAsc(doc.getId()),
                    tableRepo.findByDocumentIdOrderByIdAsc(doc.getId()));
        } catch (ResponseStatusException e) {
            throw e;
        } catch (FeignException | RestClientResponseException | ResourceAccessException e) {
            throw e;
        } catch (Exception e) {
            log.error("reparse failed, docId={}", id, e);
            throw new ResponseStatusException(HttpStatus.INTERNAL_SERVER_ERROR, "重新解析失败: " + e.getMessage());
        }
    }

    @Override
    public ChatResponse chat(ChatRequest req) {
        Map<String, Object> body = new HashMap<>();
        body.put("question", req.getQuestion());
        Map<String, String> docNameMap = new LinkedHashMap<>();

        // 与 Python RagAskRequest 一致：isolated 为 true 时必须带 doc_id，不能用 doc_ids
        boolean isolated = Boolean.TRUE.equals(req.getIsolate()) && req.getDocId() != null;
        body.put("isolated", isolated);

        if (isolated) {
            String did = String.valueOf(req.getDocId());
            body.put("doc_id", did);
            docRepo.findById(req.getDocId()).ifPresent(doc -> docNameMap.put(did, doc.getFilename()));
        } else {
            List<Document> allDocs = docRepo.findAllByOrderByIdDesc();
            Optional<Set<String>> indexedDocIds = fetchIndexedDocIds();
            List<Document> searchableDocs = allDocs.stream()
                    .filter(doc -> Objects.equals(doc.getStatus(), 1))
                    .filter(doc -> isVectorIndexed(doc, indexedDocIds))
                    .toList();
            if (searchableDocs.isEmpty()) {
                return noIndexedDocsResponse();
            }

            List<String> searchableIds = searchableDocs.stream()
                    .map(Document::getId)
                    .filter(Objects::nonNull)
                    .map(String::valueOf)
                    .toList();
            body.put("doc_ids", searchableIds);
            for (Document d : searchableDocs) {
                if (d.getId() != null && d.getFilename() != null && !d.getFilename().isBlank()) {
                    docNameMap.put(String.valueOf(d.getId()), d.getFilename());
                }
            }
        }

        if (!docNameMap.isEmpty()) {
            body.put("doc_name_map", docNameMap);
        }

        return aiClient.chat(body);
    }

    private Optional<Set<String>> fetchIndexedDocIds() {
        try {
            Map<String, Object> response = aiClient.listIndexedDocs();
            Object ids = response == null ? null : response.get("doc_ids");
            if (!(ids instanceof List<?> list)) {
                return Optional.of(Set.of());
            }
            Set<String> out = new HashSet<>();
            for (Object id : list) {
                if (id != null && !id.toString().isBlank()) {
                    out.add(id.toString().trim());
                }
            }
            return Optional.of(out);
        } catch (Exception e) {
            log.warn("无法读取 AI 引擎向量库文档列表，跨文档问答将回退到数据库文档列表", e);
            return Optional.empty();
        }
    }

    private boolean isVectorIndexed(Document doc, Optional<Set<String>> indexedDocIds) {
        if (doc.getId() == null) {
            return false;
        }
        if (indexedDocIds.isPresent()) {
            return indexedDocIds.get().contains(String.valueOf(doc.getId()));
        }
        return doc.getVectorDocId() != null;
    }

    private ChatResponse noIndexedDocsResponse() {
        ChatResponse res = new ChatResponse();
        res.setAnswer("当前没有已完成向量入库的文档，跨文档问答暂时无法检索。请重新上传或重新解析文档后再试。");
        res.setContexts(List.of());
        return res;
    }

    @Override
    public List<SearchHitVO> search(SearchRequest req) {
        List<SearchHitVO> results = new ArrayList<>();
        if (req == null || req.getKeyword() == null || req.getKeyword().isBlank()) {
            return results;
        }

        String keyword = req.getKeyword();
        Boolean isolate = req.getIsolate();
        Long docId = req.getDocId();

        // 查询文档
        List<Document> docs;
        if (Boolean.TRUE.equals(isolate) && docId != null) {
            // 隔离模式：只查当前文档
            docs = docRepo.findById(docId).map(List::of).orElse(List.of());
        } else {
            // 非隔离模式：查所有文档
            docs = docRepo.findAllByOrderByIdDesc();
        }

        // 在文档级别搜索
        for (Document doc : docs) {
            // 搜索 displayText
            if (containsKeyword(doc.getDisplayText(), keyword)) {
                SearchHitVO hit = new SearchHitVO();
                hit.setDocId(doc.getId());
                hit.setFileName(doc.getFilename());
                hit.setSnippet(extractSnippet(doc.getDisplayText(), keyword));
                results.add(hit);
            }
            // 搜索 cleanTextForRag
            else if (containsKeyword(doc.getCleanTextForRag(), keyword)) {
                SearchHitVO hit = new SearchHitVO();
                hit.setDocId(doc.getId());
                hit.setFileName(doc.getFilename());
                hit.setSnippet(extractSnippet(doc.getCleanTextForRag(), keyword));
                results.add(hit);
            }
        }

        // 在页面级别搜索
        for (Document doc : docs) {
            List<DocumentPage> pages = pageRepo.findByDocumentIdOrderByPageNoAsc(doc.getId());
            for (DocumentPage page : pages) {
                // 搜索 displayText
                if (containsKeyword(page.getDisplayText(), keyword)) {
                    SearchHitVO hit = new SearchHitVO();
                    hit.setDocId(doc.getId());
                    hit.setFileName(doc.getFilename());
                    hit.setPage(page.getPageNo());
                    hit.setSnippet(extractSnippet(page.getDisplayText(), keyword));
                    results.add(hit);
                    continue;
                }
                // 搜索 cleanTextForRag
                if (containsKeyword(page.getCleanTextForRag(), keyword)) {
                    SearchHitVO hit = new SearchHitVO();
                    hit.setDocId(doc.getId());
                    hit.setFileName(doc.getFilename());
                    hit.setPage(page.getPageNo());
                    hit.setSnippet(extractSnippet(page.getCleanTextForRag(), keyword));
                    results.add(hit);
                    continue;
                }
                // 搜索 ocrText
                if (containsKeyword(page.getOcrText(), keyword)) {
                    SearchHitVO hit = new SearchHitVO();
                    hit.setDocId(doc.getId());
                    hit.setFileName(doc.getFilename());
                    hit.setPage(page.getPageNo());
                    hit.setSnippet(extractSnippet(page.getOcrText(), keyword));
                    results.add(hit);
                }
            }
        }

        return results;
    }

    private boolean containsKeyword(String text, String keyword) {
        if (text == null || text.isBlank() || keyword == null || keyword.isBlank()) {
            return false;
        }
        return text.toLowerCase().contains(keyword.toLowerCase());
    }

    private String extractSnippet(String text, String keyword) {
        if (text == null || text.isBlank()) {
            return "";
        }
        int keywordLen = keyword.length();
        int pos = text.toLowerCase().indexOf(keyword.toLowerCase());
        if (pos < 0) {
            return text.length() > 100 ? text.substring(0, 100) + "..." : text;
        }
        int start = Math.max(0, pos - 30);
        int end = Math.min(text.length(), pos + keywordLen + 30);
        String snippet = text.substring(start, end);
        if (start > 0) {
            snippet = "..." + snippet;
        }
        if (end < text.length()) {
            snippet = snippet + "...";
        }
        return snippet;
    }

    private DocumentVO processUpload(MultipartFile file, boolean isPdf, String cleanMode) {
        log.info("开始处理文件 {}, isPdf={}, cleanMode={}", file.getOriginalFilename(), isPdf, cleanMode);

        String originalFilename = file.getOriginalFilename();
        String safeFilename = (originalFilename == null || originalFilename.isBlank())
                ? (isPdf ? "upload.pdf" : "upload.bin")
                : originalFilename;

        Document doc = new Document();
        doc.setFilename(safeFilename);
        doc.setFileType(isPdf ? "pdf" : "image");
        doc.setCleanMode(cleanMode);
        doc.setStatus(0);
        doc = docRepo.save(doc);

        try {
            Path uploadDir = Paths.get(storageBaseDir, "uploads", String.valueOf(doc.getId()));
            Files.createDirectories(uploadDir);

            Path savedPath = uploadDir.resolve(safeFilename);

            Map<String, Object> parseResult;
            if (isPdf) {
                parseResult = aiEnginePdfClient.parsePdf(file.getBytes(), safeFilename, String.valueOf(doc.getId()), cleanMode);
            } else {
                parseResult = aiClient.parseImage(file, cleanMode, String.valueOf(doc.getId()), "true");
            }

            file.transferTo(savedPath.toFile());

            log.info("AI 解析返回结果: {}", parseResult);

            fillDocumentFromParseResult(doc, parseResult);

            List<DocumentPage> pagesToSave = extractPages(parseResult, doc);
            if (!pagesToSave.isEmpty()) {
                pageRepo.saveAll(pagesToSave);
            }

            List<DocumentTable> tablesToSave = extractTables(parseResult, doc);
            if (!tablesToSave.isEmpty()) {
                tableRepo.saveAll(tablesToSave);
            }

            boolean indexed = ensureVectorIndexState(doc, parseResult);
            doc.setStatus(indexed ? 1 : 2);

        } catch (Exception e) {
            log.error("文件处理失败, docId={}", doc.getId(), e);
            doc.setStatus(2);
        }

        doc = docRepo.save(doc);
        return DocumentVoMapper.toVo(
                doc,
                pageRepo.findByDocumentIdOrderByPageNoAsc(doc.getId()),
                tableRepo.findByDocumentIdOrderByIdAsc(doc.getId()));
    }

    private void fillDocumentFromParseResult(Document doc, Map<String, Object> parseResult) throws Exception {
        if (parseResult == null) {
            return;
        }
        String raw = firstString(parseResult, "raw_ocr_text", "rawOcrText", "ocr_text");
        String display = firstString(parseResult, "display_text", "displayText", "text");
        String rag = firstString(parseResult, "clean_text_for_rag", "cleanTextForRag");
        doc.setRawOcrText(raw);
        doc.setDisplayText(display);
        doc.setCleanTextForRag(rag);
        String legacy = (display != null && !display.isBlank()) ? display : extractText(parseResult);
        doc.setOcrText(legacy);

        doc.setTableExtractStatus(firstString(parseResult, "table_extract_status", "tableExtractStatus"));

        if (parseResult.get("pages") != null) {
            doc.setPagesJson(objectMapper.writeValueAsString(parseResult.get("pages")));
        }
        if (parseResult.get("tables") != null) {
            doc.setTablesJson(objectMapper.writeValueAsString(parseResult.get("tables")));
            Map<String, Object> wrapper = new HashMap<>();
            wrapper.put("tables", parseResult.get("tables"));
            doc.setTableJson(objectMapper.writeValueAsString(wrapper));
        }
    }

    private static String firstString(Map<String, Object> map, String... keys) {
        if (map == null) {
            return null;
        }
        for (String k : keys) {
            Object v = map.get(k);
            if (v != null && !v.toString().isBlank()) {
                return v.toString();
            }
        }
        return null;
    }

    private boolean ensureVectorIndexState(Document doc, Map<String, Object> parseResult) {
        Integer chunks = parseResult == null ? null : asInteger(parseResult.get("indexed_chunks"));
        if (chunks == null || chunks <= 0) {
            chunks = indexFromParseResult(doc, parseResult);
        }

        String indexError = firstString(parseResult, "index_error", "indexError");
        if (indexError != null && !indexError.isBlank()) {
            doc.setVectorDocId(null);
            log.error("向量入库失败, docId={}, error={}", doc.getId(), indexError);
            return false;
        }

        if (chunks == null || chunks <= 0) {
            doc.setVectorDocId(null);
            log.error("向量入库未完成, docId={}, indexed_chunks={}", doc.getId(), chunks);
            return false;
        }

        doc.setVectorDocId(doc.getId());
        return true;
    }

    private Integer indexFromParseResult(Document doc, Map<String, Object> parseResult) {
        if (doc == null || doc.getId() == null || parseResult == null) {
            return null;
        }
        Object pages = parseResult.get("pages");
        if (!(pages instanceof List<?> pageList) || pageList.isEmpty()) {
            return null;
        }

        Map<String, Object> req = new LinkedHashMap<>();
        req.put("doc_id", String.valueOf(doc.getId()));
        req.put("pages", pages);
        Object tables = parseResult.get("tables");
        req.put("tables", tables instanceof List<?> ? tables : List.of());

        try {
            Map<String, Object> response = aiClient.indexKnowledge(req);
            Integer chunks = response == null ? null : asInteger(response.get("chunks"));
            if (chunks != null && chunks > 0) {
                parseResult.put("indexed_chunks", chunks);
                parseResult.remove("index_error");
                parseResult.remove("indexError");
                log.info("vector fallback indexing succeeded, docId={}, chunks={}", doc.getId(), chunks);
                return chunks;
            }
            log.error("vector fallback indexing did not complete, docId={}, response={}", doc.getId(), response);
        } catch (Exception e) {
            parseResult.put("index_error", e.getMessage());
            log.error("vector fallback indexing failed, docId={}", doc.getId(), e);
        }
        return null;
    }

    private static String guessImageContentType(String filename) {
        if (filename == null) {
            return MediaType.APPLICATION_OCTET_STREAM_VALUE;
        }
        String lower = filename.toLowerCase(Locale.ROOT);
        if (lower.endsWith(".png")) {
            return MediaType.IMAGE_PNG_VALUE;
        }
        if (lower.endsWith(".jpg") || lower.endsWith(".jpeg")) {
            return MediaType.IMAGE_JPEG_VALUE;
        }
        if (lower.endsWith(".gif")) {
            return MediaType.IMAGE_GIF_VALUE;
        }
        if (lower.endsWith(".webp")) {
            return "image/webp";
        }
        return MediaType.APPLICATION_OCTET_STREAM_VALUE;
    }

    private String extractText(Map<String, Object> parseResult) {
        if (parseResult == null) {
            return "";
        }

        Object textObj = parseResult.get("text");
        if (textObj != null && !textObj.toString().isBlank()) {
            return textObj.toString();
        }

        Object ocrTextObj = parseResult.get("ocr_text");
        if (ocrTextObj != null && !ocrTextObj.toString().isBlank()) {
            return ocrTextObj.toString();
        }

        Object pagesObj = parseResult.get("pages");
        if (pagesObj instanceof List<?> pageList) {
            StringBuilder sb = new StringBuilder();
            for (Object item : pageList) {
                if (item instanceof Map<?, ?> pageMap) {
                    Object pageText = pageMap.get("text");
                    if (pageText != null && !pageText.toString().isBlank()) {
                        sb.append(pageText).append("\n");
                        continue;
                    }

                    Object pageOcrText = pageMap.get("ocr_text");
                    if (pageOcrText != null && !pageOcrText.toString().isBlank()) {
                        sb.append(pageOcrText).append("\n");
                    }
                }
            }
            return sb.toString().trim();
        }

        return "";
    }

    private List<DocumentPage> extractPages(Map<String, Object> parseResult, Document doc) {
        List<DocumentPage> result = new ArrayList<>();
        if (parseResult == null) {
            return result;
        }
        Object pagesObj = parseResult.get("pages");
        if (!(pagesObj instanceof List<?> list)) {
            return result;
        }
        for (Object item : list) {
            if (!(item instanceof Map<?, ?> raw)) {
                continue;
            }
            DocumentPage p = new DocumentPage();
            p.setDocument(doc);
            p.setPageNo(asInteger(raw.get("page")));
            if (p.getPageNo() == null) {
                p.setPageNo(asInteger(raw.get("page_no")));
            }
            p.setImagePath(asString(raw.get("image_path")));
            p.setImageUrl(asString(raw.get("image_url")));
            p.setOcrText(asString(raw.get("text")));
            if (p.getOcrText() == null || p.getOcrText().isBlank()) {
                p.setOcrText(asString(raw.get("ocr_text")));
            }
            p.setDisplayText(asString(raw.get("display_text")));
            p.setCleanTextForRag(asString(raw.get("clean_text_for_rag")));
            p.setRawOcrText(asString(raw.get("raw_ocr_text")));

            Object linesObj = raw.get("lines");
            if (linesObj == null) {
                linesObj = raw.get("ocr_lines");
            }
            p.setOcrLinesJson(jsonString(linesObj));
            result.add(p);
        }
        return result;
    }

    private List<DocumentTable> extractTables(Map<String, Object> parseResult, Document doc) {
        List<DocumentTable> result = new ArrayList<>();
        if (parseResult == null) {
            return result;
        }
        Object tablesObj = parseResult.get("tables");
        if (!(tablesObj instanceof List<?> list)) {
            return result;
        }
        for (Object item : list) {
            if (!(item instanceof Map<?, ?> raw)) {
                continue;
            }
            DocumentTable dt = new DocumentTable();
            dt.setDocument(doc);
            dt.setPageNo(asInteger(raw.get("page")));
            if (dt.getPageNo() == null) {
                dt.setPageNo(asInteger(raw.get("page_no")));
            }
            // 按新协议读取字段：id, title, markdown, html, rows
            String tableId = asString(raw.get("id"));
            String title = asString(raw.get("title"));
            String markdown = asString(raw.get("markdown"));
            String html = asString(raw.get("html"));
            Object rowsObj = raw.get("rows");

            dt.setTableMarkdown(firstNonBlankString(markdown, raw.get("table_markdown")));

            Map<String, Object> meta = new LinkedHashMap<>();
            meta.put("id", tableId);
            meta.put("title", title);
            meta.put("html", html);
            meta.put("rows", rowsObj);
            try {
                dt.setTableJson(objectMapper.writeValueAsString(meta));
            } catch (Exception e) {
                dt.setTableJson(jsonString(meta));
            }
            result.add(dt);
        }
        return result;
    }

    private static String asString(Object o) {
        return o == null ? null : String.valueOf(o);
    }

    private static Integer asInteger(Object o) {
        if (o == null) {
            return null;
        }
        if (o instanceof Number n) {
            return n.intValue();
        }
        try {
            return Integer.parseInt(o.toString());
        } catch (NumberFormatException e) {
            return null;
        }
    }

    private static String firstNonBlankString(Object a, Object b) {
        String s = asString(a);
        if (s != null && !s.isBlank()) {
            return s;
        }
        s = asString(b);
        return (s != null && !s.isBlank()) ? s : null;
    }

    private String jsonString(Object value) {
        if (value == null) {
            return null;
        }
        try {
            return objectMapper.writeValueAsString(value);
        } catch (Exception e) {
            return value.toString();
        }
    }
}


