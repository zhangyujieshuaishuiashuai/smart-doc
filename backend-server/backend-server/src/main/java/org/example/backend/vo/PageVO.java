package org.example.backend.vo;

import lombok.Data;

@Data
public class PageVO {
    private Integer page;
    private String imagePath;
    private String imageUrl;
    private String text;
    private String displayText;
    private String cleanTextForRag;
    private String rawOcrText;
}
