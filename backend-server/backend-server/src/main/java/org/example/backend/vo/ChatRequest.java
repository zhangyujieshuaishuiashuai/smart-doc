package org.example.backend.vo;

import lombok.Data;

import java.util.List;

@Data
public class ChatRequest {
    private String question;
    private Long docId;
    private Boolean isolate;
    private List<Long> docIds;
}
