package org.example.backend.entity;

import jakarta.persistence.*;
import lombok.Data;
import java.time.LocalDateTime;

@Entity
@Table(name = "documents")
@Data
public class Document {
    @Id
    //声名主键并选择数据库自增策略
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String filename;

    /** 业务类型：image / pdf，用于重新解析时选择引擎 */
    private String fileType;

    /** 清洗模式：与 Python agent 的 clean_mode 一致 */
    private String cleanMode;

    // 存储 OCR 识别出的纯文本 (使用长文本类型)
    @Column(columnDefinition = "LONGTEXT")
    private String ocrText;

    //存储原始 OCR 识别出的纯文本 (使用长文本类型)
    @Column(columnDefinition = "LONGTEXT")
    private String rawOcrText;

    // 存储处理后的纯文本 (使用长文本类型)
    @Column(columnDefinition = "LONGTEXT")
    private String displayText;

    //存储用于 RAG 的纯文本
    @Column(columnDefinition = "LONGTEXT")
    private String cleanTextForRag;

    // 存储表格解析出的 JSON 数据（兼容旧字段）
    @Column(columnDefinition = "LONGTEXT")
    private String tableJson;

    /** Agent 返回的 tables 数组 JSON */
    @Column(columnDefinition = "LONGTEXT")
    private String tablesJson;

    /** Agent 返回的 pages 数组 JSON */
    @Column(columnDefinition = "LONGTEXT")
    private String pagesJson;

    /** Agent 表格抽取状态，如 success / partial / failed */
    private String tableExtractStatus;

    // 存储向量入库后的 ID (方便后续更新)
    private Long vectorDocId;

    private LocalDateTime createTime = LocalDateTime.now();

    // 状态：0-处理中, 1-完成, 2-失败
    private Integer status = 0;
}