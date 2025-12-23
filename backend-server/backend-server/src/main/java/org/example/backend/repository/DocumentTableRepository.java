package org.example.backend.repository;

import org.example.backend.entity.DocumentTable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface DocumentTableRepository extends JpaRepository<DocumentTable, Long> {
}
