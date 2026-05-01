package org.example.backend.controller;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;

public final class TableCsvUtil {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    private TableCsvUtil() {}

    public static String toCsv(String tableJson) {
        return toCsv(tableJson, null);
    }

    public static String toCsv(String tableJson, String tableMarkdown) {
        if ((tableJson == null || tableJson.isBlank()) && (tableMarkdown == null || tableMarkdown.isBlank())) {
            return "";
        }

        if (tableJson != null && !tableJson.isBlank()) {
            try {
                JsonNode root = MAPPER.readTree(tableJson);
                String csv = jsonToCsv(root);
                if (!csv.isBlank()) {
                    return csv;
                }
            } catch (Exception ignored) {
                // Fall back to markdown or raw JSON below.
            }
        }

        String csv = markdownToCsv(tableMarkdown);
        if (!csv.isBlank()) {
            return csv;
        }
        return tableJson == null ? "" : tableJson;
    }

    private static String jsonToCsv(JsonNode root) {
        JsonNode columns = root.get("columns");
        JsonNode rows = root.get("rows");

        if ((columns == null || rows == null) && root.get("table_json") != null) {
            JsonNode inner = root.get("table_json");
            columns = inner.get("columns");
            rows = inner.get("rows");
        }

        if (rows != null && rows.isArray() && !rows.isEmpty()) {
            JsonNode first = rows.get(0);
            if (first.isArray()) {
                return rowsArrayToCsv(rows);
            }
            if (first.isObject()) {
                return objectRowsToCsv(rows, columns);
            }
        }
        return "";
    }

    private static String rowsArrayToCsv(JsonNode rows) {
        StringBuilder sb = new StringBuilder();
        for (JsonNode row : rows) {
            if (!row.isArray()) {
                continue;
            }
            for (int i = 0; i < row.size(); i++) {
                if (i > 0) sb.append(',');
                JsonNode cell = row.get(i);
                sb.append(escape(cell == null || cell.isNull() ? "" : cell.asText("")));
            }
            sb.append('\n');
        }
        return sb.toString();
    }

    private static String objectRowsToCsv(JsonNode rows, JsonNode columnsNode) {
        List<String> columns = new ArrayList<>();
        if (columnsNode != null && columnsNode.isArray()) {
            for (JsonNode col : columnsNode) {
                columns.add(col.asText(""));
            }
        } else if (rows != null && rows.isArray() && !rows.isEmpty() && rows.get(0).isObject()) {
            rows.get(0).fieldNames().forEachRemaining(columns::add);
        }
        if (columns.isEmpty()) {
            return "";
        }

        StringBuilder sb = new StringBuilder();
        appendRow(sb, columns);
        for (JsonNode row : rows) {
            List<String> values = new ArrayList<>();
            for (String column : columns) {
                JsonNode val = row.get(column);
                values.add(val == null || val.isNull() ? "" : val.asText(""));
            }
            appendRow(sb, values);
        }
        return sb.toString();
    }

    private static String markdownToCsv(String markdown) {
        if (markdown == null || markdown.isBlank()) {
            return "";
        }

        StringBuilder sb = new StringBuilder();
        String[] lines = markdown.split("\\R");
        for (String raw : lines) {
            String line = raw == null ? "" : raw.trim();
            if (line.isBlank() || !line.contains("|")) {
                continue;
            }
            String normalized = line;
            if (normalized.startsWith("|")) {
                normalized = normalized.substring(1);
            }
            if (normalized.endsWith("|")) {
                normalized = normalized.substring(0, normalized.length() - 1);
            }
            if (isMarkdownSeparator(normalized)) {
                continue;
            }

            String[] cells = normalized.split("\\|", -1);
            List<String> values = new ArrayList<>();
            for (String cell : cells) {
                values.add(cell.trim());
            }
            appendRow(sb, values);
        }
        return sb.toString();
    }

    private static boolean isMarkdownSeparator(String line) {
        String[] cells = line.split("\\|", -1);
        if (cells.length == 0) {
            return false;
        }
        for (String cell : cells) {
            String c = cell.trim();
            if (!c.matches(":?-{3,}:?")) {
                return false;
            }
        }
        return true;
    }

    private static void appendRow(StringBuilder sb, List<String> values) {
        Iterator<String> it = values.iterator();
        boolean first = true;
        while (it.hasNext()) {
            if (!first) sb.append(',');
            first = false;
            sb.append(escape(it.next()));
        }
        sb.append('\n');
    }

    private static String escape(String s) {
        if (s == null) return "";
        String v = s.replace("\r", " ").replace("\n", " ");
        boolean needQuote = v.contains(",") || v.contains("\"");
        if (needQuote) {
            v = v.replace("\"", "\"\"");
            return "\"" + v + "\"";
        }
        return v;
    }
}
