CREATE DATABASE evaluation_db;

USE evaluation_db;

CREATE TABLE use_cases (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    success_criteria TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE tags (
    id INT AUTO_INCREMENT PRIMARY KEY,
    use_case_id INT,
    tag VARCHAR(255),
    FOREIGN KEY (use_case_id) REFERENCES use_cases(id)
);

CREATE TABLE label_files (
    id INT AUTO_INCREMENT PRIMARY KEY,
    use_case_id INT,
    file_path VARCHAR(255),
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (use_case_id) REFERENCES use_cases(id)
);

CREATE TABLE evaluation_sets (
    id INT AUTO_INCREMENT PRIMARY KEY,
    use_case_id INT,
    gold_set TEXT,
    test_set TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (use_case_id) REFERENCES use_cases(id)
);

CREATE TABLE extraction_results (
    id INT AUTO_INCREMENT PRIMARY KEY,
    use_case_id INT,
    file_path VARCHAR(255),
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (use_case_id) REFERENCES use_cases(id)
);

CREATE TABLE evaluation_iterations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    use_case_id INT,
    extraction_result_id INT,
    metrics TEXT,
    similarity_threshold FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (use_case_id) REFERENCES use_cases(id),
    FOREIGN KEY (extraction_result_id) REFERENCES extraction_results(id)
);
