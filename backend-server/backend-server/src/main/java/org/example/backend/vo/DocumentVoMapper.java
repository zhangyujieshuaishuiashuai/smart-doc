package org.example.backend.vo;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.example.backend.entity.Document;
import org.example.backend.entity.DocumentPage;
import org.example.backend.entity.DocumentTable;

import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;

public final class DocumentVoMapper {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    private DocumentVoMapper() {
    }

    public static DocumentVO toVo(Document doc, List<DocumentPage> pages, List<DocumentTable> tables) {
        DocumentVO vo = new DocumentVO();
        vo.setId(doc.getId());
        vo.setFileName(doc.getFilename());
        vo.setFileType(doc.getFileType());
        vo.setCleanMode(doc.getCleanMode());
        vo.setVectorDocId(doc.getVectorDocId());
        vo.setStatus(doc.getStatus());
        vo.setRawOcrText(doc.getRawOcrText());
        vo.setDisplayText(doc.getDisplayText());
        vo.setCleanTextForRag(doc.getCleanTextForRag());
        vo.setTableExtractStatus(doc.getTableExtractStatus());

        List<PageVO> pvs = new ArrayList<>();
        if (pages != null) {
            for (DocumentPage p : pages) {
                pvs.add(toPageVo(p));
            }
        }
        vo.setPages(pvs);

        List<TableVO> tvs = new ArrayList<>();
        if (tables != null) {
            for (DocumentTable dt : tables) {
                tvs.add(toTableVo(dt));
            }
        }
        vo.setTables(tvs);
        return vo;
    }

    private static PageVO toPageVo(DocumentPage p) {
        PageVO vo = new PageVO();
        vo.setPage(p.getPageNo());
        vo.setImagePath(p.getImagePath());
        vo.setImageUrl(p.getImageUrl());
        vo.setText(p.getOcrText());
        vo.setDisplayText(p.getDisplayText());
        vo.setCleanTextForRag(p.getCleanTextForRag());
        vo.setRawOcrText(p.getRawOcrText());
        return vo;
    }

    private static TableVO toTableVo(DocumentTable dt) {
        TableVO vo = new TableVO();
        vo.setPage(dt.getPageNo());
        vo.setMarkdown(dt.getTableMarkdown());

        String json = dt.getTableJson();
        if (json == null || json.isBlank()) {
            vo.setId(dt.getId() == null ? null : String.valueOf(dt.getId()));
            return vo;
        }
        try {
            JsonNode root = MAPPER.readTree(json);
            if (root.isObject()) {
                if (root.hasNonNull("id")) {
                    vo.setId(root.get("id").asText());
                } else {
                    vo.setId(dt.getId() == null ? null : String.valueOf(dt.getId()));
                }
                if (root.hasNonNull("title")) {
                    vo.setTitle(root.get("title").asText());
                }
                if (root.hasNonNull("html")) {
                    vo.setHtml(root.get("html").asText());
                }
                if (root.has("rows")) {
                    vo.setRows(parseRowsNode(root.get("rows")));
                }
            } else if (root.isArray()) {
                vo.setId(dt.getId() == null ? null : String.valueOf(dt.getId()));
                vo.setRows(parseRowsNode(root));
            }
        } catch (Exception ignored) {
            vo.setId(dt.getId() == null ? null : String.valueOf(dt.getId()));
        }
        return vo;
    }

    private static List<List<String>> parseRowsNode(JsonNode rowsNode) {
        if (rowsNode == null || !rowsNode.isArray()) {
            return null;
        }
        List<List<String>> rows = new ArrayList<>();
        for (JsonNode row : rowsNode) {
            if (!row.isArray()) {
                continue;
            }
            List<String> r = new ArrayList<>();
            Iterator<JsonNode> it = row.elements();
            while (it.hasNext()) {
                JsonNode cell = it.next();
                r.add(cell.isValueNode() ? cell.asText() : cell.toString());
            }
            rows.add(r);
        }
        return rows.isEmpty() ? null : rows;
    }
}
