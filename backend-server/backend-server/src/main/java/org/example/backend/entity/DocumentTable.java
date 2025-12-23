package org.example.backend.entity;

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
    private Document document;

    private Integer pageNo;

    @Column(columnDefinition = "LONGTEXT")
    private String tableJson;

    @Column(columnDefinition = "LONGTEXT")
    private String tableMarkdown;
}
