package org.example.backend.repository;

import org.example.backend.entity.DocumentPage;
import org.springframework.data.jpa.repository.JpaRepository;

public interface DocumentPageRepository extends JpaRepository<DocumentPage, Long> {
}
