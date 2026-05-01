package org.example.backend.entity;

import com.fasterxml.jackson.annotation.JsonIgnore;
import jakarta.persistence.*;
import lombok.Data;

@Entity
@Table(name = "tables")
@Data
public class DocumentTable {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "doc_id")
    @JsonIgnore
    private Document document;

    //保持轻量级，避免过度设计,PDF文档解析时记录表格物理位置
    private Integer pageNo;

    @Column(columnDefinition = "LONGTEXT")
    private String tableJson;

    @Column(columnDefinition = "LONGTEXT")
    private String tableMarkdown;
}
