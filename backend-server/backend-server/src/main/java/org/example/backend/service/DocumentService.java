package org.example.backend.service;

import org.example.backend.vo.ChatRequest;
import org.example.backend.vo.ChatResponse;
import org.example.backend.vo.DocumentVO;
import org.example.backend.vo.SearchHitVO;
import org.example.backend.vo.SearchRequest;
import org.springframework.web.multipart.MultipartFile;

import java.util.List;
import java.util.Map;

public interface DocumentService {
    DocumentVO uploadImage(MultipartFile file, String cleanMode);

    DocumentVO uploadPdf(MultipartFile file, String cleanMode);

    DocumentVO reparse(Long id, String cleanMode);

    ChatResponse chat(ChatRequest req);

    List<SearchHitVO> search(SearchRequest req);
}