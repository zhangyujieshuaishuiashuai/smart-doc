package org.example.backend.client;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.MediaType;
import org.springframework.http.client.MultipartBodyBuilder;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

import java.util.Map;

/**
 * PDF 解析不走 Feign：OpenFeign 对 multipart 的错误编码请求体会导致 Python 侧收到空文件。
 * 使用 RestClient + MultipartBodyBuilder 与浏览器/Postman 直连行为一致。
 */
@Component
public class AiEnginePdfClient {

    private final RestClient restClient;

    public AiEnginePdfClient(@Value("${ai-engine.url}") String baseUrl) {
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(10_000);
        factory.setReadTimeout(600_000);
        //动态注入 AI 引擎 URL
        this.restClient = RestClient.builder()
                .baseUrl(baseUrl)
                .requestFactory(factory)
                .build();
    }

    //PDF 文件的二进制数据（避免文件 I/O，直接内存操作）
    public Map<String, Object> parsePdf(byte[] pdfBytes, String filenameForPart, String docId, String cleanMode) {
        String fn = (filenameForPart == null || filenameForPart.isBlank()) ? "upload.pdf" : filenameForPart;
        MultipartBodyBuilder builder = new MultipartBodyBuilder();
        builder.part("file", new ByteArrayResource(pdfBytes))
                .filename(fn)
                .contentType(MediaType.APPLICATION_PDF);
        builder.part("doc_id", docId);
        builder.part("index_for_rag", "true");
        if (cleanMode != null && !cleanMode.isBlank()) {
            builder.part("clean_mode", cleanMode);
        }

        return restClient.post()
                .uri("/parse/pdf")
                .body(builder.build())
                .retrieve()
                // 解决泛型类型擦除问题，确保 Jackson 能正确将 JSON 映射为 Map<String, Object>
                .body(new ParameterizedTypeReference<Map<String, Object>>() {});
    }
}
