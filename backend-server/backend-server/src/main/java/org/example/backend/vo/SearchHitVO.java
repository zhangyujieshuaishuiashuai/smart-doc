package org.example.backend.vo;

import lombok.Data;

@Data
public class SearchHitVO {
    private Long docId;
    private String fileName;
    private Integer page;
    private String snippet;
}
