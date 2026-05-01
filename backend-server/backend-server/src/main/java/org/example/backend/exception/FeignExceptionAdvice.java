package org.example.backend.exception;

import feign.FeignException;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClientResponseException;

import java.nio.charset.StandardCharsets;

/**
 * 本类通过@RestControllerAdvice直接拦截Feign/RestClient异常，保留原始错误细节
 * 全局异常处理器，处理Feign客户端、RestClient和资源访问异常
 * 将 AI 引擎（OpenFeign、RestClient）的 HTTP/连接错误与响应体透传给前端，避免在业务层被包成无详情 500。
 */
@RestControllerAdvice
public class FeignExceptionAdvice {

    @ExceptionHandler(FeignException.class)
    public ResponseEntity<String> handleFeign(FeignException e) {
        //将http状态码转为HttpStatus枚举
        HttpStatus status = HttpStatus.resolve(e.status());
        if (status == null) {
            status = HttpStatus.BAD_GATEWAY;
        }
        //为避免二次编码直接获取原始响应体
        String raw = e.contentUTF8();
        //保留原始响应体内容可能是JSON/XML等结构化数据
        String body = (raw != null && !raw.isBlank())
                ? raw
                : "{\"detail\":\"AI 引擎请求失败\"}";//无响应体时提供标准JSON格式错误
        return ResponseEntity.status(status)
                .contentType(MediaType.APPLICATION_JSON)
                .body(body);
    }

    /**保持与handleFeign一致的错误处理逻辑，确保不同调用方式的错误表现统一 
     * PDF 解析使用 RestClient，
     * 错误需单独透传（否则会被 DocumentServiceImpl 包成 500）。 */
    @ExceptionHandler(RestClientResponseException.class)
    public ResponseEntity<String> handleRestClient(RestClientResponseException e) {
        //获取状态码
        HttpStatus status = HttpStatus.resolve(e.getStatusCode().value());
        if (status == null) {
            status = HttpStatus.BAD_GATEWAY;
        }
        String raw = e.getResponseBodyAsString(StandardCharsets.UTF_8);
        String body = (raw != null && !raw.isBlank())
                ? raw
                : "{\"detail\":\"AI 引擎请求失败\"}";
        return ResponseEntity.status(status)
                .contentType(MediaType.APPLICATION_JSON)
                .body(body);
    }

    /**处理底层网络连接异常
     * FeignException/RestClientResponseException表示已收到HTTP响应
     * ResourceAccessException表示未建立HTTP连接
     * 统一返回502状态码
     */
    @ExceptionHandler(ResourceAccessException.class)
    public ResponseEntity<String> handleResourceAccess(ResourceAccessException e) {
        String msg = e.getMessage() != null ? e.getMessage() : "无法连接 AI 引擎";
        String body = "{\"detail\":\"" + jsonEscape(msg) + "\"}";
        return ResponseEntity.status(HttpStatus.BAD_GATEWAY)
                .contentType(MediaType.APPLICATION_JSON)
                .body(body);
    }

    private static String jsonEscape(String s) {
        return s.replace("\\", "\\\\")
                .replace("\"", "\\\"")
                .replace("\r", "")
                .replace("\n", "\\n");
    }
}
