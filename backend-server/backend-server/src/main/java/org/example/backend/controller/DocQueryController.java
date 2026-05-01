package org.example.backend.controller;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import org.example.backend.client.AiEngineClient;
import org.example.backend.entity.Document;
import org.example.backend.entity.DocumentPage;
import org.example.backend.entity.DocumentTable;
import org.example.backend.repository.DocumentPageRepository;
import org.example.backend.repository.DocumentRepository;
import org.example.backend.repository.DocumentTableRepository;
import org.example.backend.service.DocumentService;
import org.example.backend.vo.DocumentVO;
import org.example.backend.vo.DocumentVoMapper;
import org.example.backend.vo.SearchHitVO;
import org.example.backend.vo.SearchRequest;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

@RestController
@RequestMapping("/api/docs")
@RequiredArgsConstructor
@CrossOrigin(origins = "*")//允许所有域的跨域请求
public class DocQueryController {
    private static final ObjectMapper MAPPER = new ObjectMapper();

    private final DocumentRepository docRepo;
    private final DocumentPageRepository pageRepo;
    private final DocumentTableRepository tableRepo;
    private final DocumentService documentService;
    private final AiEngineClient aiClient;

    @Value("${storage.base-dir:./data}")//从配置文件读取存储路径
    private String storageBaseDir;//避免硬解码路径

    @GetMapping
    public List<Document> listDocs() {
        //降序排列
        List<Document> docs = docRepo.findAllByOrderByIdDesc();
        Set<String> indexedDocIds = fetchIndexedDocIds();
        docs.forEach(doc -> markIndexedFromAgent(doc, indexedDocIds));
        return docs;
    }

    /**
     * 文档详情：与上传响应一致的 {@link DocumentVO}（含 pages / tables 新协议字段）
     */
    @GetMapping("/{docId}")
    public DocumentVO getDocDetail(@PathVariable Long docId) {
        Document doc = docRepo.findById(docId)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "文档不存在"));
        markIndexedFromAgent(doc, fetchIndexedDocIds());
        List<DocumentPage> pages = pageRepo.findByDocumentIdOrderByPageNoAsc(docId);
        List<DocumentTable> tables = tableRepo.findByDocumentIdOrderByIdAsc(docId);
        return DocumentVoMapper.toVo(doc, pages, tables);
    }

    /**
     * 全局搜索接口
     * 将搜索请求委托给服务层
     */
    @PostMapping("/search")
    public List<SearchHitVO> search(@RequestBody SearchRequest req) {
        return documentService.search(req);
    }

    //直接返回页面数据
    @GetMapping("/{docId}/pages")
    public List<DocumentPage> listPages(@PathVariable Long docId) {
        return pageRepo.findByDocumentIdOrderByPageNoAsc(docId);
    }

    @GetMapping("/{docId}/tables")
    public List<DocumentTable> listTables(@PathVariable Long docId) {
    return tableRepo.findByDocumentIdOrderByIdAsc(docId);
}

    @GetMapping(value = "/{docId}/tables/{tableId}/csv", produces = "text/csv;charset=UTF-8")
    public ResponseEntity<String> downloadTableCsv(@PathVariable Long docId, @PathVariable String tableId) {
        DocumentTable table = resolveTable(docId, tableId);
        if (table == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "table not found");
        }

        String csv = TableCsvUtil.toCsv(table.getTableJson(), table.getTableMarkdown());
        String safeName = ("doc-" + docId + "-table-" + tableId + ".csv")
                .replaceAll("[\\\\/:*?\"<>|\\r\\n]", "_");
        return ResponseEntity.ok()
                .contentType(MediaType.parseMediaType("text/csv;charset=UTF-8"))
                .header(HttpHeaders.CONTENT_DISPOSITION, "attachment; filename=\"" + safeName + "\"")
                .body("\uFEFF" + csv);
    }


    @GetMapping(value = "/{docId}/pages/{pageNo}/image", produces = MediaType.IMAGE_PNG_VALUE)
    public Resource getPageImage(@PathVariable Long docId, @PathVariable Integer pageNo) {
        Path p = Paths.get(storageBaseDir, "pages", String.valueOf(docId), "page_" + pageNo + ".png");
        return new FileSystemResource(p.toFile());
    }

    @GetMapping("/{docId}/pages/{pageNo}/text")
    public String getPageText(@PathVariable Long docId, @PathVariable Integer pageNo) {
        return pageRepo.findByDocumentIdAndPageNo(docId, pageNo)
                .map(DocumentPage::getOcrText)
                .orElse("");
    }

    private DocumentTable resolveTable(Long docId, String tableId) {
        if (docId == null || tableId == null || tableId.isBlank()) {
            return null;
        }
        String wanted = tableId.trim();
        List<DocumentTable> tables = tableRepo.findByDocumentIdOrderByIdAsc(docId);
        for (DocumentTable table : tables) {
            if (table.getId() != null && String.valueOf(table.getId()).equals(wanted)) {
                return table;
            }
            String logicalId = tableLogicalId(table);
            if (wanted.equals(logicalId)) {
                return table;
            }
        }
        return null;
    }

    private String tableLogicalId(DocumentTable table) {
        String json = table == null ? null : table.getTableJson();
        if (json == null || json.isBlank()) {
            return null;
        }
        try {
            JsonNode root = MAPPER.readTree(json);
            JsonNode id = root.get("id");
            return id == null || id.isNull() ? null : id.asText();
        } catch (Exception ignored) {
            return null;
        }
    }

    private Set<String> fetchIndexedDocIds() {
        try {
            Map<String, Object> response = aiClient.listIndexedDocs();
            Object ids = response == null ? null : response.get("doc_ids");
            if (!(ids instanceof List<?> list)) {
                return Set.of();
            }
            Set<String> out = new HashSet<>();
            for (Object id : list) {
                if (id != null && !id.toString().isBlank()) {
                    out.add(id.toString().trim());
                }
            }
            return out;
        } catch (Exception ignored) {
            return Set.of();
        }
    }

    private void markIndexedFromAgent(Document doc, Set<String> indexedDocIds) {
        if (doc == null || doc.getId() == null || doc.getVectorDocId() != null) {
            return;
        }
        if (indexedDocIds.contains(String.valueOf(doc.getId()))) {
            doc.setVectorDocId(doc.getId());
        }
    }
}
