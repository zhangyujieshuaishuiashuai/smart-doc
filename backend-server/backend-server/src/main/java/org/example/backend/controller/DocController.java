package org.example.backend.controller;

import lombok.RequiredArgsConstructor;
import org.example.backend.service.DocumentService;
import org.example.backend.vo.ChatRequest;
import org.example.backend.vo.ChatResponse;
import org.example.backend.vo.DocumentVO;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.util.Map;

//restful api不需要视图渲染，处理文档上传、重新解析和聊天请求,返回json
@RestController
@RequestMapping("/api/docs")
@RequiredArgsConstructor
//跨域问题
@CrossOrigin(origins = "*")
public class DocController {

    private final DocumentService documentService;

    @PostMapping("/upload/image")
    public DocumentVO uploadImage(@RequestParam("file") MultipartFile file,
                                  @RequestParam(value = "clean_mode", defaultValue = "general") String cleanMode) {
        return documentService.uploadImage(file, cleanMode);
    }

    @PostMapping("/upload/pdf")
    public DocumentVO uploadPdf(@RequestParam("file") MultipartFile file,
                                @RequestParam(value = "clean_mode", defaultValue = "paper") String cleanMode) {
        return documentService.uploadPdf(file, cleanMode);
    }

    @PostMapping("/{id}/reparse")
    public DocumentVO reparse(@PathVariable Long id, @RequestBody Map<String, String> body) {
        String cleanMode = "general";
        if (body != null) {
            cleanMode = body.getOrDefault("clean_mode", body.getOrDefault("cleanMode", "general"));
        }
        return documentService.reparse(id, cleanMode);
    }

    @PostMapping("/chat")
    public ChatResponse chat(@RequestBody ChatRequest request) {
        return documentService.chat(request);
    }
}
//仅处理http逻辑