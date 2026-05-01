package org.example.backend.client;
//Feign远程服务客户端客户端接口，用于与外部AI引擎服务进行通信
import org.example.backend.vo.ChatResponse;
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.multipart.MultipartFile;

import java.util.Map;

@FeignClient(name = "ai-engine", url = "${ai-engine.url}")
public interface AiEngineClient {

    @PostMapping(value = "/parse/image", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    //指定接收multipart表单数据格式
    Map<String, Object> parseImage(@RequestPart("file") MultipartFile file,
                                   @RequestPart("clean_mode") String cleanMode,
                                   @RequestPart(value = "doc_id", required = false) String docId,
                                   @RequestPart(value = "index_for_rag", required = false) String indexForRag);

    /** Python 侧为 POST /rag/ask，字段 isolated / doc_id / doc_ids 与 RagAskRequest 一致 */
    @PostMapping("/rag/ask")
    ChatResponse chat(@RequestBody Map<String, Object> req);

    @PostMapping("/knowledge/index")
    Map<String, Object> indexKnowledge(@RequestBody Map<String, Object> req);

    @GetMapping("/knowledge/docs")
    Map<String, Object> listIndexedDocs();
}
