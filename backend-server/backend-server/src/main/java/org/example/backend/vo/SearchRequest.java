package org.example.backend.vo;

import lombok.Data;

@Data
public class SearchRequest {
    private String keyword;
    private Boolean isolate;
    private Long docId;
}
