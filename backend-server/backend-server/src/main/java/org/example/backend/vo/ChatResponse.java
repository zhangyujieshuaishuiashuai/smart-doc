package org.example.backend.vo;

import lombok.Data;

@Data
public class ChatResponse {
    private String answer;
    private Object contexts;
}
