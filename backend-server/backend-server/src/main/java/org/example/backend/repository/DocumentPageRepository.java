package org.example.backend.repository;
//文档的数据访问接口
import org.example.backend.entity.DocumentPage;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;


public interface DocumentPageRepository extends JpaRepository<DocumentPage, Long> {
    /**根据文档ID和页码查询单页内容
    作用：精确获取指定文档的特定页码内容（用于分页文档的随机访问）
    */
    Optional<DocumentPage> findByDocumentIdAndPageNo(Long docId, Integer pageNo);

    /**根据文档ID查询所有页内容并排序
    作用：获取指定文档的所有页内容并排序
    */
    // ✅ 给 DocQueryController 用
    List<DocumentPage> findByDocumentIdOrderByPageNoAsc(Long docId);
}
