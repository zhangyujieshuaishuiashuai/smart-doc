package org.example.backend.vo;

import lombok.Data;

import java.util.List;

@Data
public class TableVO {
    private String id;
    private Integer page;
    private String title;
    private String markdown;
    private String html;
    private List<List<String>> rows;
}
