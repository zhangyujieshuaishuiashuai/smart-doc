package org.example.backend.repository;

import org.example.backend.entity.Document;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
//处理 OpenFeign 调用产生的异常
public interface DocumentRepository extends JpaRepository<Document, Long> {
    //按最新创建顺序展示文档
    List<Document> findAllByOrderByIdDesc();
}
