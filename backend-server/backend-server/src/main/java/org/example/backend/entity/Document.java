package org.example.backend.entity;

import jakarta.persistence.*;
import lombok.Data;
import java.time.LocalDateTime;

@Entity
@Table(name = "documents")
@Data
public class Document {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String filename;

    // 存储 OCR 识别出的纯文本 (使用长文本类型)
    @Column(columnDefinition = "LONGTEXT")
    private String ocrText;

    // 存储表格解析出的 JSON 数据
    @Column(columnDefinition = "LONGTEXT")
    private String tableJson;

    // 存储向量入库后的 ID (方便后续更新)
    private Long vectorDocId;

    private LocalDateTime createTime = LocalDateTime.now();

    // 状态：0-处理中, 1-完成, 2-失败
    private Integer status = 0;
}