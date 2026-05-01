package org.example.backend.repository;

import org.example.backend.entity.DocumentTable;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface DocumentTableRepository extends JpaRepository<DocumentTable, Long> {
    //保证表格数据按创建顺序排列
    List<DocumentTable> findByDocumentIdOrderByIdAsc(Long docId);
}
