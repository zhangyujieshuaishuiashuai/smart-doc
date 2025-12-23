package org.example.backend.entity;

import jakarta.persistence.*;
import lombok.Data;

@Entity
@Table(name = "document_pages")
@Data
public class DocumentPage {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "doc_id")
    private Document document;

    private Integer pageNo;

    @Column(columnDefinition = "LONGTEXT")
    private String ocrText;

    private String imagePath;
}
