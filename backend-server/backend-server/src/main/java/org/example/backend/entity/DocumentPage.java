package org.example.backend.entity;

import org.aspectj.weaver.loadtime.Agent;

import com.fasterxml.jackson.annotation.JsonIgnore;
import jakarta.persistence.*;
import lombok.Data;

@Entity
@Table(name = "document_pages")
@Data
public class DocumentPage {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    //同属于一个文档的多页信息采取慢加载策略避免查询文档时立即加载所有页面
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "doc_id")
    @JsonIgnore
    private Document document;

    private Integer pageNo;

    @Column(columnDefinition = "LONGTEXT")
    private String ocrText;

    /**
     * PaddleOCR 原始行级结果（JSON 字符串），用于“页图定位高亮”。
     * 形如：[{"text":"...","score":0.98,"box":[[x,y],...]}]
     */
    @Column(columnDefinition = "LONGTEXT")
    private String ocrLinesJson;

    

    private String imagePath;

    /**存储agent生成的公网URL 
     * Agent 返回的可访问页图 URL，优先于本地拼接路径 */
    private String imageUrl;

    @Column(columnDefinition = "LONGTEXT")
    private String displayText;

    @Column(columnDefinition = "LONGTEXT")
    private String cleanTextForRag;

    @Column(columnDefinition = "LONGTEXT")
    private String rawOcrText;
}
