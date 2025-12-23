package org.example.backend.client;

import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.multipart.MultipartFile;
import java.util.Map;

// 这里的 name 随便起，url 读取配置文件里的 ai-engine.url
@FeignClient(name = "ai-engine", url = "${ai-engine.url}")
public interface AiEngineClient {

    // 1. 调用 OCR
    @PostMapping(value = "/ocr/image", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    Map<String, Object> ocrImage(@RequestPart("file") MultipartFile file);

    // 2. 调用表格解析
    @PostMapping(value = "/extract/pdf-table", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    Map<String, Object> extractTable(@RequestPart("file") MultipartFile file);

    // 3. 调用向量入库 (传 JSON)
    @PostMapping(value = "/vector/add", consumes = MediaType.APPLICATION_JSON_VALUE)
    Map<String, Object> addVector(@RequestBody Map<String, Object> request);

    // 4. 调用向量搜索 (传 JSON)
    @PostMapping(value = "/vector/search", consumes = MediaType.APPLICATION_JSON_VALUE)
    Map<String, Object> searchVector(@RequestBody Map<String, Object> request);
}