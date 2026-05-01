package org.example.backend.vo;

import lombok.Data;

import java.util.List;

@Data
public class DocumentVO {
    private Long id;
    private String fileName;
    private String fileType;
    private String cleanMode;
    private Long vectorDocId;
    private Integer status;

    private String rawOcrText;
    private String displayText;
    private String cleanTextForRag;

    private String tableExtractStatus;

    private List<PageVO> pages;
    private List<TableVO> tables;
}
